# TASK 69 — "A100 rebrand" quick-add: one selectable action queues the correct DEVID records on correct rows

Repo `/home/raza/nvidia/pico-ga100vfi`, main. Console: `host/ga100vfi/console/service.py` + `gui.py` (HTML/JS embedded). Read `evidence/66-ux-review.md` for context; task 68 just made "Arm & burn queue" the single burn trigger — build on that state (pull latest main first).

## Feature (owner request, verbatim intent)
"there should be a section for adding the correct A100 DEVID, user shouldn't have to work it through, selectable option to add to the burn queue, intelligent enough to add it to the correct row."

FOLLOW-UP OWNER NOTE (supersedes the new-block idea): the "Suggested burns" panel ALREADY has "+ Queue DEVID A/B pair" with a free-text DEVID hex input — the manual hex is the error surface. UPGRADE THAT CONTROL in place (do not add a second DEVID block): replace the free-text input with a **SKU dropdown** — `A100 80GB PCIe (0x20B5)` / `A100 40GB PCIe (0x20F1)` / `custom…` (custom reveals the old hex box, kept as advanced fallback). The button then fetches the server plan (words + rows) for the selected SKU and queues both records. Default selection: 80GB. The dropdown choice, not typed hex, is the normal path — no manual hex for the common case.

## Semantics (ground truth — encode exactly)
- FF word = data16<<16 | fuse_offset<<6 | chain. DEVIDA = offset 37, DEVIDB = offset 38, chain 2.
- SKUs: "A100 80GB PCIe (0x20B5)" → data 0x20B5 → words 0x416A0942 / 0x416A0982. "A100 40GB PCIe (0x20F1)" → data 0x20F1 → words 0x20F10942 / 0x20F10982.
- Rows: the FF region is replayed last-wins-per-block, so the row is a SLOT — correct row = first free FF rows chosen by the server, honoring the existing placement policy (ff_policy: below IFF_RECORD start, no bit5, blank target, never the burned-card scattered zone rules already encoded there). Reuse the same layout scan the "first free FF row" button uses — server-side this time, returning BOTH rows in order (DEVIDA first, then DEVIDB on the next free row).

## Implementation
1. service.py: `GET /api/rebrand/plan?sku=80|40` → {records:[{row, value, old:0, label:"DEVIDA → 0x20B5"},{row, value, old:0, label:"DEVIDB → 0x20B5"}]} computed from live layout + ff_policy (validate each returned placement through ff_policy before returning; error if fewer than 2 legal rows). Mock mode: return deterministic mock rows.
2. gui.py: upgrade the Suggested-burns DEVID control in place — SKU dropdown (default 80GB) replacing the free-text box (custom… reveals it); "+ Queue DEVID A/B pair" GETs the plan for the selected SKU and appends both records to the queue (same queue structure custom records use), statuses pending, decode labels shown. Refuse (with note) if the queue already contains either word.
3. Tests: extend/new `host/tests/test_rebrand_plan.py` (unittest): word arithmetic for both SKUs (assert exact hex), mock-mode endpoint returns 2 records passing ff_policy, duplicate-add refusal is client-side (test the JS logic exists via marker). Baseline FAIL-set must stay identical (pre-existing: test_burn_window/test_program_sequence/test_verify6 TypeError, test_verify8 KeyError, test_task17 8/13). py_compile + node --check on extracted JS.
4. Deploy to HP (192.168.0.175, sshpass pw khankhan, sudo via `echo khankhan | sudo -S bash -c`; root-owned clone: scp→/tmp→sudo cp; restart via `sudo bash -c 'systemctl restart ga100-fuse-console &'`, poll /api/gpus; GETs only — live card). Verify served page contains the SKU dropdown markers ("A100 80GB PCIe" and "A100 40GB PCIe") and md5 parity of both files.
5. Commit on main (no push), TASKS.md board line, marker TASK69_DONE + 8-line summary.

## Rules
- Do not weaken any burn gate; this feature only PLANS queue entries — burning still goes through Arm & burn queue.
- Never hardcode row 313/314 as the answer — rows come from the live layout (313/314 is just what tonight's card happened to yield).
