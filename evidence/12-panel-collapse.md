# Task 12 — driver-bound capture panel: collapse/expand + consent cancel

Date: 2026-11-23. Worktree /tmp/v12 from main (a12be09 == fork/main). gui.py only.

## Diff summary

`host/ga100vfi/console/gui.py | 38 ++++++++++++++++++++++++++++++++++++--` (36 insertions, 2 deletions), four hunks:

1. `LIVEBAR` template: new `<div class="card verdict warnv" id="boundbar"
   style="display:none;margin-top:8px;padding:6px 14px"></div>` directly after
   `#boundpanel` — same warnv card styling as the panel, slimmer padding.
2. `boundHide()` now also hides `#boundbar` (driver-unbound / no-capture path
   hides panel AND bar). New `boundBar(j)`: hides the panel (and resets
   `dataset.bound="0"`), renders the one-line bar
   `Fuse capture available (driver bound) — last dump <age>. [Expand ▾]`
   using the existing `pill warnl` / `note` / `btn` classes and the existing
   `fmtAge()`. Expand click removes the `ga100.boundCollapsed` flag, hides the
   bar and calls `fetchLive(false)` — `dataset.bound` is `"0"`, so
   `boundPanel()` rebuilds the full panel on that poll.
3. `boundPanel()`: after the `manual_dump_available` check,
   `localStorage.getItem("ga100.boundCollapsed") === "1"` → `boundBar(j)` and
   return (collapse state survives polls; bar age refreshes each poll).
   Otherwise the bar is hidden and the panel rebuilds as before. Header row is
   now a flex row with a `Collapse ▴` button; its handler sets
   `ga100.boundCollapsed="1"`, calls `boundHide()`, then `boundBar(j)` so the
   bar appears immediately, not only on the next poll.
4. `boundConsent()`: consent row gains `Cancel` (`#boundcancel`) which sets
   `#boundconsent` display:none only — outer panel, dataset and result div
   untouched.

Collapse flag is cleared on Expand (requirement 4: not persistent forever).
No backend change; service.py untouched; VERSION stays 0.3.0.

## Mock render check (real served HTML, not py_compile)

Mock console on 127.0.0.1:58363 (`python3 -m ga100vfi.console --mock
/tmp/v12_mock.json`, mock = STUB dump). `curl /` then grep counts in the
served page:

| pattern | count |
|---|---|
| `Collapse ▴` | 1 |
| `Expand ▾` | 1 |
| `boundcancel">Cancel` | 1 |
| `id="boundbar"` | 1 |
| `ga100.boundCollapsed` | 3 (set / remove / check) |
| `Fuse capture available (driver bound)` | 1 |

`/api/live` returned the live JSON (`{"live": true, "bdf": "?", ...}`) —
unchanged. Server killed after the check (curl to it now fails).

## Gates

- `python3 -m py_compile host/ga100vfi/console/gui.py` — clean;
  `import ga100vfi.console.gui, ga100vfi.console.service` — OK.
- JS syntax: extracted the generated page's main `<script>` block (124 053
  chars, regex `<script>…</script>` on the built live HTML — extraction was
  clean) → `node --check` passed.
- Fingerprint (`version_info()`, sha256 over version.py+fusedump.py+service.py+gui.py):
  baseline on a12be09 `c3218843a4d8` → after change `7c42414320a6`;
  version still `0.3.0`.
- Not hardware-verified (UI-only change; no card involved).

## HTML/JS excerpts (as served)

```html
<div class="card verdict warnv" id="boundbar" style="display:none;margin-top:8px;padding:6px 14px"></div>
```

```js
if (localStorage.getItem("ga100.boundCollapsed") === "1") { boundBar(j); return; }
...
`<button class="btn" id="boundcollapse">Collapse ▴</button></div>` +
...
document.getElementById("boundexpand").onclick = () => {
  localStorage.removeItem("ga100.boundCollapsed");
  bar.style.display = "none";
  fetchLive(false);   // dataset.bound is "0" — next poll rebuilds the panel now
};
```
