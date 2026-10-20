"""Embeddings: Amazon Titan on Bedrock, with a deterministic local
hashed-bag-of-words fallback so offline demos keep hybrid search working."""

import hashlib
import json
import math
import re

import numpy as np

from app.config import settings

LOCAL_DIM = 384
_TOKEN = re.compile(r"[a-z0-9]+")


def stem(token: str) -> str:
    """Tiny deterministic stemmer so 'stacks' and 'stack' match."""
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in _TOKEN.findall(text.lower())]

_client = None


def _bedrock():
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.demo_mode:
        return [local_embed(t) for t in texts]
    try:
        return [_bedrock_embed(t) for t in texts]
    except Exception:
        return [local_embed(t) for t in texts]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def _bedrock_embed(text: str) -> list[float]:
    body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
    resp = _bedrock().invoke_model(
        modelId=settings.bedrock_embed_model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    return json.loads(resp["body"].read())["embedding"]


def local_embed(text: str) -> list[float]:
    vec = np.zeros(LOCAL_DIM, dtype=np.float32)
    tokens = tokenize(text)
    if not tokens:
        return vec.tolist()
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % LOCAL_DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec.tolist()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va.dot(vb) / denom) if denom else 0.0
