# TASK 04 — Support-bundle polish: real git sha + zero-dumps warning

Branch fuse-console, base HEAD ffbd97d. Run 2026-11-22.

## Change (host/ga100vfi/console/service.py only)

1. `_repo_git_sha()` -> `_git_sha_and_source()`:
   - `git -C <pkg>/../.. rev-parse HEAD` where `<pkg>` =
     `Path(__file__).resolve().parents[1]` (the installed `ga100vfi` package
     dir), via `sh()` argv list, timeout 5 s. Package-relative, not CWD —
     production runs with CWD=/opt/ga100-fuse-view which is not a git repo.
   - Fallback: read `<pkg>/.git_sha` (deploy artifact), validated
     `[0-9a-f]{40}`.
   - Final fallback `("unknown", "unknown")`.
   - Returns `(sha, source)`, source in {"git", "file", "unknown"}.
2. `support_bundle()` manifest: `tool_git_sha` from the helper, new field
   `git_sha_source`.
3. `support_bundle()`: when `_bundle_dump_dirs()` is empty, warnings gain
   `"no complete dumps found in state dir (dump.json missing in all dump
   dirs)"` — distinguishes "nothing collected" from "collection failed".

## Gate 1 — py_compile — PASS

```
$ python3 -m py_compile host/ga100vfi/console/service.py
COMPILE_OK
```

## Gate 2 — local mock instance, port 8793, temp state dir, NO dumps — PASS

```
$ PYTHONPATH=host python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json \
    --state-dir /tmp/v04-state --listen 127.0.0.1 --port 8793 --poll 5   # PID 2384492
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8793/
GET / -> 200
$ curl -s http://127.0.0.1:8793/api/support_bundle -o /tmp/v04-bundle.tar.gz
bundle -> 200
```

manifest.json from the returned tar.gz:

```
tool_git_sha   = ffbd97d2fd3dc062f72435a1538e379d40726ab5   (== local HEAD)
git_sha_source = git
warnings       = ['console.log not present in state dir',
                  'goldilocks.jsonl not present in state dir',
                  'last-preview.json not present in state dir',
                  'no complete dumps found in state dir (dump.json missing in all dump dirs)']
dump members   = []
ALL ASSERTIONS PASS
```

## Gate 3 — production shape (no git above package) — PASS

```
$ cp -r host/ga100vfi /tmp/pkg_nogit/
$ echo 0123456789abcdef0123456789abcdef01234567 > /tmp/pkg_nogit/ga100vfi/.git_sha
$ git -C /tmp/pkg_nogit rev-parse HEAD
fatal: not a git repository (or any parent up to mount point /)
$ PYTHONPATH=/tmp/pkg_nogit python3 -c \
    "from ga100vfi.console.service import _git_sha_and_source; print(_git_sha_and_source())"
('0123456789abcdef0123456789abcdef01234567', 'file')
```

## Gate 4 — dashboard serves — PASS

`GET / -> 200` (shown under Gate 2, same instance).

## Gate 5 — instance killed by PID — PASS

```
$ kill 2384492
$ curl -s -m 2 http://127.0.0.1:8793/   -> connection refused
instance down
```

## Notes

- `docs/CONSOLE.md:345` describes manifest.json generically ("tool git SHA")
  and stays accurate; the new `git_sha_source` field is not named there.
  Task hard rule scoped this commit to service.py, so docs untouched.
- No firmware/ changes, no AI2 access, no force push.
