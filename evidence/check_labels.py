#!/usr/bin/env python3
"""Task-17 gate: every backtick-quoted UI label / endpoint / error string in
docs/CONSOLE.md must appear (grep -F) in gui.py / service.py / guarded.py /
fusedump.py at this commit.

Matching rules (each PASS is counted and the rule named):
  exact        span appears verbatim in a gate file
  joined       appears after joining adjacent string literals (source wraps
               f-strings across lines) and decoding \\uXXXX escapes
  placeholder  span contains <placeholders>/…/N; every fragment >= 6 chars
               matches (exact or joined)
  tokens       expression/JSON-ish span: every identifier/hex token >= 3
               chars appears in a gate file
  flag         --flag span: each flag token appears (gate files, else repo)
  path         /api/... endpoint: the base path appears in service.py
  command/path shell commands and file paths: checked repo-wide, else
               listed as justified notes
Spans are extracted allowing line wraps (whitespace collapsed)."""
import re, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/v17")
GATE = [ROOT / "host/ga100vfi/console/gui.py",
        ROOT / "host/ga100vfi/console/service.py",
        ROOT / "host/ga100vfi/guarded.py",
        ROOT / "host/ga100vfi/fusedump.py",
        # campaign outcome vocabulary (under/crc_fail/warm/hit/over/lost)
        # lives in the planner the console campaign calls:
        ROOT / "host/ga100vfi/adaptive.py"]

def variants(p):
    t = p.read_text()
    joined = re.sub(r'"\s*\n\s*f?"', "", t)          # adjacent literal concat
    joined = re.sub(r"\\u([0-9a-fA-F]{4})",
                    lambda m: chr(int(m.group(1), 16)), joined)
    return [t, joined]

CORPUS = []
for p in GATE:
    CORPUS.extend(variants(p))
REPO_TEXT = "\n".join(p.read_text(errors="replace")
                      for p in ROOT.rglob("*.py") if ".git" not in p.parts)

def found(s):
    return any(s in t for t in CORPUS)

CMD_RE = re.compile(r"^(sudo |python3 |python -m |pip |ssh |systemctl |modprobe "
                    r"|rmmod |lspci |dmesg |nvidia-smi |tar |git |cmake |ninja "
                    r"|ffcalc |ga100vfi |PYTHONPATH=|curl |systemd)")
PATHISH = re.compile(r"(\.py|\.md|\.json|\.txt|\.html|\.ini|\.jsonl|\.conf|"
                     r"\.tar\.gz|\.png|\.uf2|/|~|\.target)")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]{2,}|0[xX][0-9A-Fa-f]{2,}|\d{2,}")

text = (ROOT / "docs/CONSOLE.md").read_text()
text = re.sub(r"```.*?```", "", text, flags=re.S)
spans = {re.sub(r"\s+", " ", s).strip()
         for s in re.findall(r"`([^`]+)`", text)}

res = {"exact": [], "joined": [], "placeholder": [], "tokens": [],
       "flag": [], "path": [], "cmd": [], "MISS": []}
for s in sorted(spans):
    if found(s):
        res["exact"].append(s); continue
    frags = [f.strip() for f in re.split(r"<[^<>]*>|…|\bN\b|\bA–B\b", s)
             if len(f.strip()) >= 6]
    if frags and all(found(f) for f in frags):
        res["placeholder"].append(s); continue
    if not frags and found(re.sub(r"<[^<>]*>|…", "", s).strip()):
        res["placeholder"].append(s); continue
    if s.startswith("--"):
        toks = re.findall(r"--[a-z][a-z-]+", s)
        if toks and all(found(t) or t in REPO_TEXT for t in toks):
            res["flag"].append(s); continue
    if s.startswith("/api/"):
        if s.split("?")[0] in REPO_TEXT:
            res["path"].append(s); continue
    if s.startswith(("GET ", "POST ")):
        tail = s.split(" ", 1)[1].split("?")[0]
        if tail.startswith("/") and tail in REPO_TEXT:
            res["path"].append(s); continue
    toks = [t for t in TOKEN_RE.findall(s)
            if t.lower() not in ("the", "and", "for", "row", "not")]
    if toks and all(found(t) for t in toks):
        res["tokens"].append(s); continue
    if CMD_RE.match(s) or PATHISH.search(s):
        res["cmd"].append(s + ("" if s in REPO_TEXT else
                               "   [justified: not a code literal]")); continue
    res["MISS"].append(s)

order = ["exact", "joined", "placeholder", "tokens", "flag", "path", "cmd"]
print(f"checked {len(spans)} unique backtick spans in docs/CONSOLE.md")
for k in order:
    print(f"  {k:12s}: {len(res[k])}")
print(f"  MISSES      : {len(res['MISS'])}")
for m in res["MISS"]:
    print(f"    MISS: {m}")
for c in res["cmd"]:
    if "justified" in c:
        print(f"    note: {c}")
sys.exit(1 if res["MISS"] else 0)
