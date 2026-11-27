# Task 14 — vertical left tab rail (gui.py layout)

Date: 2026-11-23. Worktree /tmp/v14 from main (f21dfdf), branch v14,
commit 5920cf1 "console: vertical left tab rail with responsive horizontal
fallback". Only host/ga100vfi/console/gui.py changed (diff 111 lines;
`grep -c switchTab` on the diff = 0 — JS untouched).

## HTML restructure (excerpt of the diff)

```diff
   </header>
+  </div>
+__LIVEBAR__
+  <div class="layout">
   <nav class="tabs" role="tablist" aria-label="console views">
...
   </nav>
-  </div>
-__LIVEBAR__
+  <main class="content">
   <section id="tab-explorer" class="tabpane on" ...>
...
   <section id="tab-gpu" class="tabpane" ...>
     ...
   </section>
+  </main>
+  </div>
```

.sticktop now wraps ONLY the topbar; __LIVEBAR__ sits between .sticktop and
.layout (full-width, sticky below the topbar as before). nav.tabs is the
first child of .layout; the 4 tabpane sections moved inside
<main class="content"> with ids/roles/aria unchanged. auditbg/footer stay
after .layout.

## CSS (excerpt of the diff)

```diff
+  .layout { display: flex; align-items: flex-start; gap: 18px; }
+  .content { flex: 1 1 auto; min-width: 0; }
...
-  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border);
-          margin-bottom: 14px; }
+  .tabs { display: flex; flex-direction: column; align-items: stretch;
+          gap: 2px; width: 190px; flex: 0 0 190px;
+          position: sticky; top: var(--sticktop, 0px);
+          max-height: calc(100vh - var(--sticktop, 0px) - 16px);
+          overflow-y: auto; z-index: 15; padding: 6px 0; }
+  .tab { background: none; border: none; text-align: left; ...
+         padding: 8px 12px; min-height: 34px; ...
+         border-left: 2px solid transparent;
+         border-radius: 0 6px 6px 0; ... }
-  .tab.on { color: var(--accent); border-bottom-color: var(--accent); }
+  .tab.on { color: var(--accent); border-left-color: var(--accent); }
```

Responsive fallback (served CSS, verbatim):

```css
  @media (max-width: 860px) {
    .layout { flex-direction: column; }
    .tabs { flex-direction: row; width: auto; flex: none;
            position: sticky; top: var(--sticktop, 0px); z-index: 15;
            overflow-x: auto; background: var(--bg);
            border-bottom: 1px solid var(--border); margin-bottom: 14px;
            max-height: none; padding: 0; }
    .tab { text-align: center; padding: 9px 15px 8px; min-height: 0;
           border-left: none; border-bottom: 2px solid transparent;
           margin-bottom: -1px; border-radius: 6px 6px 0 0; }
    .tab.on { border-left-color: transparent;
              border-bottom-color: var(--accent); }
  }
```

ResizeObserver JS unchanged: still publishes --sticktop from .sticktop
(topbar only now), so #livebar (z-20) and the rail (z-15) both park below it.
.tab:focus-visible ring rule untouched (line list unchanged).

## Gates (all run in /tmp/v14)

- `python3 -m py_compile host/ga100vfi/console/gui.py` → PASS;
  `from ga100vfi.console import gui` import OK.
- Mock console: `python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json
  --port 8799 --listen 127.0.0.1` → `/` HTTP 200, `/api/live` HTTP 200.
  Server killed after; port 8799 connection-refused confirmed.
- Wrap verification (python html.parser + regex on the SERVED page):
  first child of .layout = `('nav', None, 'tabs')`; `<main class="content">`
  contains all 4 `id="tab-*" class="tabpane` sections and no tabpane exists
  outside it; livebar offset lies between sticktop and layout in the markup.
- `node --check` on <script> extracted from the mock-served page → PASS.
- CSS sanity on served CSS: `.tabs { ... flex-direction: column ... }`
  present; `@media (max-width: 860px)` present; awk scan of every `.tab.on`
  rule: BASE rule has only `border-left-color`, the bottom-border indicator
  appears only IN-MEDIA. No leftover underline outside the media query.
- Fingerprint: `/api/live` → `version 0.3.0`, `fingerprint 4c44059b43db`
  (was ea31e19599dc) — changed as expected, version unchanged (no bump).
- Push: `f21dfdf..5920cf1 v14 -> main` on fork, non-force (HTTPS via
  GIT_ASKPASS with GITHUB_TOKEN from ~/.hermes/.env, token not printed).
  `git ls-remote fork main` → 5920cf143f426c811d458ea70965aaf7680c9ce9.

## Not verified

- No browser on this machine (no chrome/headless_shell): sticky offsets,
  rail scroll behaviour at depth, and the 860px breakpoint were verified by
  CSS/markup inspection only, not rendered pixels.
