# Task 13 — sticky tab bar (topbar + tabs frozen while scrolling)

- Branch `v13` from `main` (7e5f4aa) in worktree `/tmp/v13`; commit `f21dfdf`
  "console: sticky tab bar — topbar+tabs frozen while scrolling" (gui.py only,
  +23/-1). Pushed `v13:main` to fork (no force); ls-remote confirms
  `refs/heads/main = f21dfdf5eb96bca119c63ddca9077751d07ec7d5`. Local `main`
  moved to f21dfdf; worktree removed. Primary tree untouched (still
  fuse-console 320c85c, dirty pwmvid.c).

## Premise correction (task brief vs code)

The brief said `.topbar` has `position: sticky; ... z-index: 1` at ~line 140.
In the code at 7e5f4aa that rule belongs to `th` (sticky table headers inside
the `.scroll` overflow containers — a different feature, kept untouched).
`.topbar` (gui.py:104) had NO sticky rule, so there was nothing to remove
from it; the wrapper alone provides the freeze.

## Diff excerpts (host/ga100vfi/console/gui.py)

CSS — new single sticky container (no overflow, so `.tab.on` underline and
`:focus-visible` ring are not clipped):

```css
+  .sticktop { position: sticky; top: 0; z-index: 30; background: var(--bg); }
```

#livebar parks below it (default 0px = old behaviour if JS never runs):

```css
-  #livebar { margin-bottom: 14px; position: sticky; top: 0; z-index: 20;
+  #livebar { margin-bottom: 14px; position: sticky; top: var(--sticktop, 0px); z-index: 20;
```

HTML — one wrapper around header + nav (z 30 > livebar z 20):

```html
 <div class="app">
+  <div class="sticktop">
   <header class="topbar">
   ...
   </nav>
+  </div>
 __LIVEBAR__
```

JS (appended in the existing <script>, switchTab logic untouched;
feature-checked — without ResizeObserver the livebar just sticks at 0):

```js
+const sticktopEl = document.querySelector(".sticktop");
+if (sticktopEl && window.ResizeObserver) {
+  const setSticktop = () => document.documentElement.style.setProperty(
+      "--sticktop", sticktopEl.getBoundingClientRect().height + "px");
+  new ResizeObserver(setSticktop).observe(sticktopEl);
+  setSticktop();
+}
```

## Gates

- `python -m py_compile host/ga100vfi/console/gui.py` — PASS.
  `from ga100vfi.console import gui` — PASS (HTML len 74431).
- `node --check` on the <script> block extracted from the MOCK-SERVED page
  (124,602 bytes) — PASS.
- Mock console: `python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json
  --port 8797 --listen 127.0.0.1` → `/` HTTP 200, `/api/live` HTTP 200.
  Server killed after (port 8797 connection-refused confirmed).
- Wrap verification (region extraction from served HTML, not grep counts):
  regex-extracted `<div class="app"> ... <section id="tab-explorer"` region;
  asserted index(`<div class="sticktop">`) < index(`<header class="topbar">`)
  < index(`<nav class="tabs"`) < index(`</div>` after `</nav>`) — PASS
  ("WRAP_OK: sticktop opens before header, closes after </nav>").
  Served page contains `--sticktop` and `ResizeObserver`; served livebar rule
  shows `top: var(--sticktop, 0px)`.
- Headless render check: SKIPPED — `which chromium chromium-browser
  google-chrome google-chrome-stable headless_shell chrome` → none found.
  No screenshot/getBoundingClientRect check was possible on this machine.
- Fingerprint: `/api/live` version block → `version 0.3.0`,
  `fingerprint ea31e19599dc` (was 7c42414320a6) — changed as expected,
  version unchanged (no VERSION bump).
- Push: `7e5f4aa..f21dfdf v13 -> main` on fork, non-force (HTTPS via
  GIT_ASKPASS with GITHUB_TOKEN from ~/.hermes/.env, token not printed;
  same convention as evidence/09). `git ls-remote` main = f21dfdf.

## Not verified

Visual freeze/scroll behaviour (no headless browser available); the
ResizeObserver path was syntax-checked and served, not executed in a browser.
