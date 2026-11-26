"""Write site/data/repo_map.json: every folder and source file of the project with its size and first doc line."""
import ast
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = ["backend", "research_discovery", "matlab", "frontend", "scripts", "tests", "notebooks", "docs", ".github/workflows"]
EXT = {".py": "Python", ".js": "JavaScript", ".m": "MATLAB", ".html": "HTML", ".css": "CSS", ".md": "Markdown",
       ".yml": "Workflow", ".ipynb": "Notebook", ".json": "JSON"}


def first_line(path, ext):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return ""
    if ext == ".py":
        try:
            doc = ast.get_docstring(ast.parse(text))
        except SyntaxError:
            doc = None
        return (doc or "").strip().split("\n")[0]
    if ext == ".m":
        m = re.search(r"^%\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""
    if ext == ".md":
        m = re.search(r"^#\s+(.+)$", text, re.M)
        return m.group(1).strip() if m else ""
    if ext == ".yml":
        m = re.search(r"^name:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""
    if ext == ".html":
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        return m.group(1).strip() if m else ""
    return ""


def main():
    out, totals = [], {}
    tests = 0
    for d in DIRS:
        base = os.path.join(ROOT, d)
        for dirpath, dirnames, files in os.walk(base):
            dirnames[:] = sorted(x for x in dirnames if not x.startswith((".", "__")) and x not in ("fonts", "figures", "media", "deck"))
            for f in sorted(files):
                ext = os.path.splitext(f)[1]
                if ext not in EXT or (ext == ".json" and d != "data"):
                    continue
                p = os.path.join(dirpath, f)
                text = open(p, encoding="utf-8", errors="ignore").read()
                lines = text.count("\n") + 1
                if ext == ".py" and "/tests/" in p.replace("\\", "/") or f.startswith("test_"):
                    tests += len(re.findall(r"^\s*def test_", text, re.M))
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                out.append({"path": rel, "lang": EXT[ext], "lines": lines, "about": first_line(p, ext)[:160]})
                totals[EXT[ext]] = totals.get(EXT[ext], 0) + lines
    folders = {}
    for r in out:
        parts = r["path"].split("/")
        top = "/".join(parts[:2]) if len(parts) > 2 and parts[0] in (".github", "research_discovery", "backend") else parts[0]
        f = folders.setdefault(top, {"folder": top, "files": 0, "lines": 0})
        f["files"] += 1
        f["lines"] += r["lines"]
    data = {"files": out, "folders": sorted(folders.values(), key=lambda x: -x["lines"]), "lines_by_language": totals,
            "test_functions": tests, "workflows": sum(1 for r in out if r["lang"] == "Workflow"),
            "docs": sum(1 for r in out if r["lang"] == "Markdown")}
    os.makedirs(os.path.join(ROOT, "site", "data"), exist_ok=True)
    json.dump(data, open(os.path.join(ROOT, "site", "data", "repo_map.json"), "w"), indent=1)
    print(len(out), "files", data["test_functions"], "tests", data["lines_by_language"])


if __name__ == "__main__":
    main()
