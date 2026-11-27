# Task 16 — Widen the scrollable content column

Date: 2026-11-23. Worktree /tmp/v16 from main (4028120). gui.py CSS only,
one commit ce7a6f1 "console: widen content column — app cap 1780px, slimmer
status rail". Primary tree and AI2 untouched.

## CSS diff (gui.py, 5 insertions / 5 deletions)

```diff
-  .app { max-width: 1140px; padding: 20px 22px 48px; }
+  .app { max-width: min(1780px, 100%); padding: 20px 22px 48px; }
-  .content { flex: 1 1 auto; min-width: 0; } /* min-width:0: wide tables/pre
-     blocks must not blow out the flex row */
+  .content { flex: 1 1 auto; min-width: 0; width: 100%; } /* min-width:0: wide
+     tables/pre blocks must not blow out the flex row */
-  .siderail { flex: 0 0 380px; width: 380px; position: sticky;
+  .siderail { flex: 0 0 360px; width: 360px; position: sticky;
-    .siderail { flex-basis: 320px; width: 320px; } }
+    .siderail { flex-basis: 300px; width: 300px; } }
```

Unchanged as required: `@media (min-width: 1200px) { .app { margin: 0 auto; } }`
(centering), the 860px stacked fallback, sticky/frozen rails.

Effect on a 1780px-wide viewport: content column grows from ~530px to
~1780 − 44 (padding) − 190 (tabs) − 360 (rail) − 36 (gaps) ≈ 1150px.

## Gates

- `python -m py_compile host/ga100vfi/console/gui.py`: PASS.
  `from ga100vfi.console import gui`: imports OK.
- Mock console on free port 8797 (`python3 -m ga100vfi.console --mock
  /tmp/card1_fuse_dump.json --port 8797`):
  - `GET /` → HTTP 200 (155183 bytes); `GET /api/live` → HTTP 200.
  - Served-page grep (counts, all on the mock-served HTML, not the source):
    `max-width: min(1780px, 100%)` ×1, `flex: 0 0 360px; width: 360px` ×1,
    `flex-basis: 300px; width: 300px` ×1, `min-width: 1200px` ×1,
    `max-width: 860px` ×1, `id="livebar"` ×1 (no escape breakage).
  - `node --check` on the single `<script>` block extracted from the served
    page: OK.
  - Server killed after checks.
- Fingerprint / version: baseline at 4028120 was `ee5f139b2847`; at the new
  commit `version_info()` → version `0.3.0`, fingerprint `8bf8e2a2ed3f`
  (changed, as expected — gui.py is one of the four fingerprint files).
  Version NOT bumped.

## Ship

- Push fork main 4028120..ce7a6f1, no force. `git ls-remote fork main` →
  `ce7a6f19586e1c2d3522bf69bf29d2df8898e980`. Local `main` fast-forwarded to
  ce7a6f1. Worktree removed.
