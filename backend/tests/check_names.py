"""Static sanity check: module-level names referenced but never imported/defined.

Catches the damage that text-merging modules can cause (dropped imports) without
needing the runtime to execute every path.
"""
import ast
import builtins
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "self", "cls"}


def module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                # plain and tuple-unpacked targets, e.g. a = 1 / a, b = fn()
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.For):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    names.add(n.id)
        elif isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    names.add(n.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
            names.add(node.optional_vars.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


problems = 0
for dirpath, _dirs, files in os.walk(ROOT):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, path)
        defined = module_names(tree) | BUILTINS
        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
        missing = sorted(used - defined)
        if missing:
            problems += len(missing)
            rel = os.path.relpath(path, ROOT)
            print(f"[FAIL] {rel}: undefined -> {', '.join(missing)}")

print("\nUNDEFINED-NAME CHECK: " + ("OK" if problems == 0 else f"{problems} problem(s)"))
sys.exit(0 if problems == 0 else 1)