# TASK 15 — Right-side status rail: livebar fixed right, content scrolls freely

Base: main = 5920cf1 (== fork/main). Worktree /tmp/v15. Primary tree and AI2 untouched.

## Change (host/ga100vfi/console/gui.py only, +25/-10)

1. `__LIVEBAR__` moved from above `.layout` to inside it, wrapped as the third
   child: `</main>` → `<aside class="siderail" id="siderail">__LIVEBAR__</aside>` → `</div>`.
2. New `.siderail` CSS (sticky rail, 380px, own scroll area):

   ```
   .siderail { flex: 0 0 380px; width: 380px; position: sticky;
               top: calc(var(--sticktop, 0px) + 8px); align-self: flex-start;
               max-height: calc(100vh - var(--sticktop, 0px) - 16px);
               overflow-y: auto; z-index: 15; }
   .siderail:empty { display: none; }
   ```

   `:empty` hides the rail in static (non-live) builds, where the placeholder
   substitutes nothing (verified: static aside is exactly
   `<aside class="siderail" id="siderail"></aside>`, no whitespace).
3. `#livebar` lost `position: sticky; top: var(--sticktop, 0px); z-index: 20;`
   — the rail is the sticky element now; card styling kept.
4. `@media (max-width: 1200px) { .siderail { flex-basis: 320px; width: 320px; } }`
   added so mid-width windows don't squeeze the center.
5. `@media (max-width: 860px)` extended: `.siderail { flex: none; width: auto;
   position: static; max-height: none; order: -1; }` and `.tabs` gained
   `order: -2` — narrow order is tabs, siderail, content (tabs stay first).
6. ResizeObserver / `--sticktop` JS, switchTab, bound* JS untouched. No
   backend change, no VERSION bump. Two stale comments naming the sticky
   `#livebar` updated to the side rails.

## Gate — py_compile + imports: PASS

`python -m py_compile host/ga100vfi/console/gui.py` → ok;
`import ga100vfi.console.gui, ga100vfi.console.service` → IMPORTS_OK.

## Gate — mock console (port 8796, --mock /tmp/card1_fuse_dump.json): PASS

- `GET /` → HTTP 200 (155159 bytes); `GET /api/live` → HTTP 200.
- html.parser region extraction on the served page:
  - `.layout` children (in order): `nav.tabs`, `main.content`, `aside.siderail#siderail`
  - `id="livebar"` inside `aside.siderail`: True
  - tabpanes inside `main.content`: tab-explorer, tab-glitch, tab-drivers, tab-gpu
  - `id="livebar"` occurs exactly once in the page.
- `node --check` on the script extracted from the served page: OK.
- Server killed after checks.

### Caught by the mock gate (fixed before commit)

First draft's CSS comment contained the literal token `__LIVEBAR__`;
`build_html`'s `.replace()` injected the whole livebar HTML into the
`<style>` block (page had 2× `id="livebar"`, one inside CSS). Comment
reworded; re-served page verified clean. py_compile alone would not have
caught this.

## Gate — CSS grep on served page: PASS

- `.siderail { flex: 0 0 380px; ... position: sticky;` present (line 43).
- `@media (max-width: 1200px)` with `.siderail { flex-basis: 320px; width: 320px; }` present.
- `#livebar { margin-bottom: 14px; background: ... }` — no `position: sticky`.
- 860px block contains `.siderail { flex: none; width: auto; position: static; max-height: none; order: -1; }`.
- ids intact in served page: livebar, boundpanel, boundbar, pollsel, gpusel, feed.

## Gate — fingerprint / version: PASS

- Baseline recomputed from `git show main:` over the four fingerprint files:
  `4c44059b43db` (matches expected).
- After change: `version_info()` → `0.3.0 281fde1a32ad` — fingerprint changed,
  version unchanged.
