"""Vector + keyword index.

- OpenSearchIndex: used when DEMO_MODE=false (BM25 + kNN hybrid, time-gated filter).
- LocalIndex: deterministic offline fallback (BM25 + cosine on hashed vectors)
  so the full demo runs with no infrastructure.
Both expose: add_chunks(), search(), delete_course(), count().
"""

import json
import math
import os
import re
import threading

from app.config import settings
from app.services import embeddings

TOKEN = re.compile(r"[a-z0-9]+")
MIN_RELEVANCE = 0.5  # below this a "match" is noise, not evidence


def time_filter_clause(video_time: float | None) -> dict | None:
    """OpenSearch filter: non-video sources always allowed; video only if start_time <= t."""
    if video_time is None:
        return None
    return {
        "bool": {
            "should": [
                {"bool": {"must_not": [{"term": {"source_type": "video"}}]}},
                {"range": {"start_time": {"lte": float(video_time)}}},
            ],
            "minimum_should_match": 1,
        }
    }


class LocalIndex:
    """File-backed BM25 + vector index (one JSON file per course)."""

    def __init__(self, root: str | None = None):
        self.root = root or os.path.join(settings.upload_dir, "index")
        self._lock = threading.Lock()

    def _path(self, course_id: str) -> str:
        return os.path.join(self.root, f"{course_id}.json")

    def _load(self, course_id: str) -> list[dict]:
        p = self._path(course_id)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, course_id: str, docs: list[dict]) -> None:
        os.makedirs(self.root, exist_ok=True)
        tmp = self._path(course_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False)
        os.replace(tmp, self._path(course_id))

    def add_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        course_id = chunks[0]["course_id"]
        with self._lock:
            docs = self._load(course_id)
            ids = {d["chunk_id"] for d in docs}
            for c in chunks:
                if c["chunk_id"] in ids:
                    continue
                doc = dict(c)
                doc["embedding"] = embeddings.embed_query(c["text"])
                doc["terms"] = embeddings.tokenize(c["text"])
                docs.append(doc)
            self._save(course_id, docs)

    def delete_course(self, course_id: str) -> None:
        with self._lock:
            if os.path.exists(self._path(course_id)):
                os.remove(self._path(course_id))

    def count(self, course_id: str) -> int:
        return len(self._load(course_id))

    def search(
        self,
        course_id: str,
        query: str,
        video_time: float | None = None,
        top_k: int = 6,
        time_gate: bool = True,
    ) -> list[dict]:
        docs = self._load(course_id)
        if not docs:
            return []
        q_tokens = embeddings.tokenize(query)
        q_vec = embeddings.embed_query(query)
        avgdl = sum(len(d["terms"]) for d in docs) / max(len(docs), 1)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d["terms"]):
                df[t] = df.get(t, 0) + 1
        n = len(docs)
        results = []
        for d in docs:
            if time_gate and video_time is not None:
                if d.get("source_type") == "video" and (d.get("start_time") or 0) > float(video_time):
                    continue
            # BM25
            score = 0.0
            tf: dict[str, int] = {}
            for t in d["terms"]:
                tf[t] = tf.get(t, 0) + 1
            k1, b = 1.5, 0.75
            for t in q_tokens:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
                freq = tf[t]
                score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * len(d["terms"]) / avgdl))
            vec_score = embeddings.cosine(q_vec, d.get("embedding") or [])
            final = 0.65 * score + 0.9 * max(vec_score, 0.0)
            if final <= 0.0001:
                continue
            out = {k: v for k, v in d.items() if k not in ("terms", "embedding")}
            out["_score"] = final
            results.append(out)
        results.sort(key=lambda r: r["_score"], reverse=True)
        return results[:top_k]


class OpenSearchIndex:
    INDEX = "learn2hire_chunks"

    def __init__(self):
        from opensearchpy import OpenSearch, RequestsHttpConnection

        auth = None
        if settings.opensearch_user:
            auth = (settings.opensearch_user, settings.opensearch_password)
        self.client = OpenSearch(
            hosts=[settings.opensearch_url],
            http_auth=auth,
            use_ssl=settings.opensearch_url.startswith("https"),
            verify_certs=False,
            connection_class=RequestsHttpConnection,
            timeout=30,
        )
        self._ensure_index()

    def _ensure_index(self) -> None:
        if self.client.indices.exists(index=self.INDEX):
            return
        self.client.indices.create(
            index=self.INDEX,
            body={
                "settings": {"index": {"knn": True}},
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "course_id": {"type": "keyword"},
                        "material_id": {"type": "keyword"},
                        "source_type": {"type": "keyword"},
                        "source_name": {"type": "text"},
                        "start_time": {"type": "float"},
                        "end_time": {"type": "float"},
                        "page": {"type": "integer"},
                        "slide": {"type": "integer"},
                        "text": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 1024,
                            "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "nmslib"},
                        },
                    }
                },
            },
        )

    def add_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        vecs = embeddings.embed_texts([c["text"] for c in chunks])
        from opensearchpy import helpers

        actions = []
        for c, v in zip(chunks, vecs):
            doc = dict(c)
            doc["embedding"] = v if len(v) == 1024 else embeddings.local_embed(c["text"]) + [0.0] * 640
            if len(doc["embedding"]) != 1024:
                doc["embedding"] = (doc["embedding"] + [0.0] * 1024)[:1024]
            actions.append({"_index": self.INDEX, "_id": c["chunk_id"], "_source": doc})
        helpers.bulk(self.client, actions, refresh=True)

    def delete_course(self, course_id: str) -> None:
        self.client.delete_by_query(
            index=self.INDEX, body={"query": {"term": {"course_id": course_id}}}, refresh=True
        )

    def count(self, course_id: str) -> int:
        resp = self.client.count(index=self.INDEX, body={"query": {"term": {"course_id": course_id}}})
        return resp.get("count", 0)

    def search(
        self,
        course_id: str,
        query: str,
        video_time: float | None = None,
        top_k: int = 6,
        time_gate: bool = True,
    ) -> list[dict]:
        filters: list[dict] = [{"term": {"course_id": course_id}}]
        tf = time_filter_clause(video_time) if time_gate else None
        if tf:
            filters.append(tf)

        q_vec = embeddings.embed_query(query)
        if len(q_vec) != 1024:
            q_vec = (q_vec + [0.0] * 1024)[:1024]

        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "filter": filters,
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {
                                        "multi_match": {
                                            "query": query,
                                            "fields": ["text^2", "source_name"],
                                        }
                                    },
                                    {"knn": {"embedding": {"vector": q_vec, "k": top_k * 3}}},
                                ],
                                "minimum_should_match": 1,
                            }
                        }
                    ],
                }
            },
        }
        try:
            resp = self.client.search(index=self.INDEX, body=body)
        except Exception:
            body["query"]["bool"]["must"] = [
                {"multi_match": {"query": query, "fields": ["text^2", "source_name"]}}
            ]
            resp = self.client.search(index=self.INDEX, body=body)

        out = []
        for hit in resp["hits"]["hits"]:
            doc = hit["_source"]
            doc["_score"] = hit["_score"]
            out.append(doc)
        return out


_index = None


def get_index():
    global _index
    if _index is None:
        if settings.demo_mode:
            _index = LocalIndex()
        else:
            try:
                _index = OpenSearchIndex()
            except Exception:
                _index = LocalIndex()
    return _index


# ========================= time-gated retrieval =========================

def search(
    course_id: str,
    query: str,
    video_time: float | None,
    top_k: int | None = None,
time_gate: bool = True,
) -> list[dict]:
    idx = get_index()
    k = top_k or settings.top_k
    results = idx.search(course_id, query, video_time=video_time, top_k=k * 2, time_gate=time_gate)
    # post-filter guarantee on top of the index-level gate (no spoilers, ever)
    if time_gate and video_time is not None:
        results = [
            r
            for r in results
            if not (r.get("source_type") == "video" and (r.get("start_time") or 0) > float(video_time))
        ]
    return results[:k]


def retrieve_for_question(
    course_id: str, question: str, video_time: float | None, history: list[dict] | None = None
) -> dict:
    """Return gated evidence plus the honest 'covered later' signal."""
    rewrite = _rewrite_query(question, history)
    gated = [r for r in search(course_id, rewrite, video_time, time_gate=True) if _relevant(r)]

    if gated:
        return {"query": rewrite, "chunks": gated, "covered_later": False}

    # Nothing passed the relevance bar inside the gate. Before telling the learner the
    # topic is "later", check whether it is in fact ALREADY covered but simply scored
    # low (wording mismatch) — we must not wrongly refuse to answer taught material.
    ungated = search(course_id, rewrite, None, top_k=12, time_gate=False)
    already_covered = [
        r
        for r in ungated
        if _loosely_relevant(r)
        and (
            video_time is None
            or r.get("source_type") != "video"
            or (r.get("start_time") or 0) <= float(video_time)
        )
    ]
    if already_covered:
        return {"query": rewrite, "chunks": already_covered[: settings.top_k], "covered_later": False}

    future = [
        r
        for r in ungated
        if video_time is not None
        and r.get("source_type") == "video"
        and (r.get("start_time") or 0) > float(video_time)
        and _loosely_relevant(r)
    ]
    return {"query": rewrite, "chunks": [], "covered_later": bool(future)}

def _loosely_relevant(chunk: dict) -> bool:
    """Relaxed relevance bar, used only to decide between 'answer' and 'covered later'."""
    return chunk.get("_score", 0) >= MIN_RELEVANCE * 0.35

def _relevant(chunk: dict) -> bool:
    return chunk.get("_score", 0) >= MIN_RELEVANCE

def _rewrite_query(question: str, history: list[dict] | None) -> str:
    """Lightweight query clarification: keep it local (no model call needed)."""
    q = question.strip()
    if len(q) < 12 and history:
        last = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
        if last:
            q = f"{q} (context: {last[:160]})"
    return q
