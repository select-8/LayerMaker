#!/usr/bin/env python3
import re, os, ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Heuristics and patterns
WIN_ABS = re.compile(r'(?i)\b([A-Z]:\\[^"\']+)')
POSIX_ABS = re.compile(r'(?<![A-Za-z0-9_])(/[^"\']+)')
LIKELY_ROOT_VAR = re.compile(r'(?:^|_)(dir|root|path|base|folder|home|drive|mapfiles|pmsmap|yamls?)(_?|$)', re.I)
KEYWORDS = re.compile(r'(?i)\b(pms[-_ ]?maps|mapfiles|mapserver|LayerMaker|yamleditor|grid_yamls|prime2|wfs)\b')
ARGPARSE_DEFAULT = re.compile(r'(?i)parser\.add_argument\([^)]*default\s*=\s*([^\s,)]+)')

# For AST inspection of simple assignments like pmsmap_dir = "C:\\DevOps\\pms-maps"
def literal_string_assigns(tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # Only handle simple Name targets
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not names: 
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                out.append((names, node.value.value, node.lineno))
    return out

def find_os_path_joins(code):
    # crude scan for os.path.join("C:\\..", ...) or Path("C:/...") etc.
    hits = []
    for m in re.finditer(r'os\.path\.join\(([^)]*)\)|Path\(([^)]*)\)', code):
        span = m.group(1) or m.group(2) or ""
        if WIN_ABS.search(span) or POSIX_ABS.search(span):
            hits.append((m.start(), span))
    return hits

def scan_file(pyfile: Path):
    rel = pyfile.relative_to(ROOT)
    report = []
    try:
        src = pyfile.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return rel, [f"[ERROR] {e}"]

    # 1) plain literal paths
    for rx, label in [(WIN_ABS, "WIN_ABS"), (POSIX_ABS, "POSIX_ABS")]:
        for m in rx.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            snippet = m.group(1)
            # ignore trivial POSIX like '/n' from regex negatives
            if label == "POSIX_ABS" and snippet.strip() in ("/",):
                continue
            report.append(f"{label}: L{line}: {snippet}")

    # 2) keywords
    for m in KEYWORDS.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        snippet = src[m.start():m.end()]
        report.append(f"KEYWORD: L{line}: {snippet}")

    # 3) argparse defaults
    for m in ARGPARSE_DEFAULT.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        val = m.group(1)
        if val.startswith(("'", '"')):
            val_str = val.strip('"\'')

            if WIN_ABS.search(val_str) or POSIX_ABS.search(val_str) or KEYWORDS.search(val_str):
                report.append(f"ARGPARSE_DEFAULT: L{line}: {val_str}")
        else:
            report.append(f"ARGPARSE_DEFAULT: L{line}: {val}")

    # 4) AST assignments like pmsmap_dir = "C:\\DevOps\\pms-maps"
    try:
        tree = ast.parse(src)
        for names, val, lineno in literal_string_assigns(tree):
            for n in names:
                if LIKELY_ROOT_VAR.search(n) or KEYWORDS.search(val) or WIN_ABS.search(val) or POSIX_ABS.search(val):
                    report.append(f"ASSIGN: L{lineno}: {n} = {val}")
    except SyntaxError:
        pass

    # 5) os.path.join / Path() with absolute bases
    for pos, args in find_os_path_joins(src):
        line = src.count("\n", 0, pos) + 1
        report.append(f"JOIN_ABS_BASE: L{line}: {args.strip()}")

    # De-dup, keep order
    seen = set()
    final = []
    for item in report:
        if item not in seen:
            final.append(item)
            seen.add(item)

    return rel, final

def is_ignored(p: Path):
    parts = set(p.parts)
    if any(x in parts for x in {".git", ".venv", "venv", "__pycache__", "build", "dist"}):
        return True
    return False

def main():
    any_hits = False
    for pyfile in sorted(ROOT.rglob("*.py")):
        if is_ignored(pyfile):
            continue
        rel, items = scan_file(pyfile)
        if items:
            any_hits = True
            print(f"\n=== {rel} ===")
            for it in items:
                print(it)
    if not any_hits:
        print("No path-related items found.")

if __name__ == "__main__":
    main()
