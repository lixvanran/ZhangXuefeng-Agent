#!/usr/bin/env python3
"""Static check: resolve every internal `from app...` import against the real tree.
No third-party deps needed - pure AST + filesystem. Catches dangling references
left behind by refactors (e.g. the wrong_book removal)."""
import ast
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
PKG = os.path.join(ROOT, "app")

# Build a set of importable module names from the filesystem
modules = set()
for dirpath, dirnames, filenames in os.walk(PKG):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    rel = os.path.relpath(dirpath, ROOT).replace(os.sep, ".")
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        stem = fn[:-3]
        if stem == "__init__":
            modules.add(rel)
        else:
            modules.add(f"{rel}.{stem}")

# Names actually defined (functions/classes/vars) per module
defined = {}
for dirpath, dirnames, filenames in os.walk(PKG):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT).replace(os.sep, ".")[:-3]
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        except SyntaxError as e:
            print(f"[SYNTAX ERROR] {rel}: {e}")
            continue
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.asname or a.name.split(".")[0])
        defined[rel] = names

problems = []
for rel, names in sorted(defined.items()):
    path = os.path.join(ROOT, rel.replace(".", os.sep) + ".py")
    if not os.path.exists(path):
        path = os.path.join(ROOT, rel.replace(".", os.sep), "__init__.py")
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                continue
            mod = node.module or ""
            if not mod.startswith("app"):
                continue
            if mod not in modules:
                problems.append(f"{rel}:{node.lineno}  module NOT FOUND: from {mod} import ...")
                continue
            if mod in defined:
                for a in node.names:
                    if a.name == "*":
                        continue
                    if a.name not in defined[mod]:
                        problems.append(
                            f"{rel}:{node.lineno}  name NOT FOUND: from {mod} import {a.name}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("app") and a.name not in modules:
                    problems.append(f"{rel}:{node.lineno}  module NOT FOUND: import {a.name}")

print(f"scanned {len(defined)} internal modules\n")
if problems:
    print(f"!! {len(problems)} unresolved internal import(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("OK: all internal app.* imports resolve")
