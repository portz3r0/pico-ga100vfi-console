# Task 32 — per-burn selection with last-wins-aware already-present marking

Date: 2026-11-24. Worktree /tmp/v32, branch `v32` off main `269b0bf`;
change is `host/ga100vfi/console/gui.py` only (server unchanged).
Tool fingerprint `dda39a2011d5` (was `4620be9b2088`), VERSION `0.3.0` —
both read live from `GET :56628/api/live` (`{"version":"0.3.0",
"git_sha":"269b0bf…","fingerprint":"dda39a2011d5"}`).

Design (predecessor, unchanged here): shared `lastWinsStatus(word)` /
`directStepPresent(step)` helpers; `planSel`/`advSel` hold only explicit
user choices — default = selected unless the word is EFFECTIVE under
last-wins (present → default OFF, superseded → ON); select-all/none
affordances; every queue path and the proposal row allocator honour the
selection; force-queued present words get the amber queue tag
`⚠ already present — likely no-op (row N)`; advanced items badge
`ALREADY PRESENT` / `PARTIALLY PRESENT (k/n: …)`.

## Gate: t32 — 34/34 PASS (cases a–e)

Playwright against mock `:56628` (`--mock /tmp/newcard.json`) and mockfx
`:56629` (`--mock /tmp/pw32/fixture-dump.json`, synth card with the
superseded-at-row-301 block-8 record). Run 2026-11-24, task-32b re-run.

(a) present word → badge, default UNchecked, excluded from rows/queue:

    PASS a_present_badge | ALREADY PRESENT (row 300) — no burn needed … target row: not selected — not queued
    PASS a_default_unchecked
    PASS a_excluded_from_proposed_rows | ["281+282","283+284","285+286"]
    PASS a_excluded_from_queue | ["281+282","283+284","285+286"]
    PASS a_panel_shares_badge_and_selection

(b) superseded word (exact match at row 300, later block-8 record at 301)
→ badge, default CHECKED, queueable, no no-op warn:

    PASS b_superseded_badge | SUPERSEDED at row 301 — needs re-burn … target row: row 302 → 0x00100201 + mirror row 303
    PASS b_default_checked
    PASS b_all_four_placed | ["302+303","281+282","283+284","285+286"]
    PASS b_superseded_queued | ["302+303","281+282","283+284","285+286"]
    PASS b_queue_no_warn_for_superseded

(c) deselect one of 4 → queue exactly 3, rows == proposed rows;
select-none/select-all round-trip; panel shares selection:

    PASS c_proposed_rows_drop_deselected | ["302+303","281+282","283+284"]
    PASS c_summary_reflects_selection | 3 of 4 word(s) selected in 3 record group(s)
    PASS c_queue_exactly_3_equals_proposed | queue=["302+303","281+282","283+284"] proposed=["302+303","281+282","283+284"]
    PASS c_select_none_no_rows | []
    PASS c_select_all_restores_4 | ["304+305","285+286","287+288","289+290"]
    PASS c_panel_shares_selection

(d) advanced items on the real card: Gen4 all-present (3 FF words each
`ALREADY PRESENT (row 327/328/329)`, item badge `ALREADY PRESENT — no
burn needed`, steps default unchecked, queue-when-none-selected adds
nothing, one re-checked step gets row 330+331 and the queue holds exactly
that word); PLM direct-row bitmap present (all 3 DIRECT delta steps
present → item `ALREADY PRESENT — no burn needed`); compute partial:

    PASS d_gen4_all_present | ALREADY PRESENT — no burn needed …
    PASS d_plm_direct_all_present | ALREADY PRESENT — no burn needed …
    PASS d_compute_partially_present | PARTIALLY PRESENT (11/16: 0x80070141, 0x06010181, 0x018001C1, 0x00000241, 0x000002C1, 0x00000341, 0x00000381, 0x420004C1 …
    PASS d_compute_absent_words_not_listed
    PASS d_gen4_steps_default_unchecked
    PASS d_gen4_queue_nothing_when_none_selected
    PASS d_one_step_selected_gets_row | ["gen4-permanent:330+331"]
    PASS d_queue_exactly_the_selected_word | ["330+331"]

(e) force-queued already-present word → warn tag in the queue, queue ==
proposed:

    PASS e_present_badge_glitch_tab
    PASS e_default_unchecked
    PASS e_recheck_gets_row | ["302+303","281+282","283+284","285+286"]
    PASS e_queue_warn_tag | already present — likely no-op (row 300) …
    PASS e_queue_equals_proposed | queue=["302+303","281+282","283+284","285+286"] proposed=["302+303","281+282","283+284","285+286"]

    PASS mock_index_200
    PASS mock_has_advanced_and_plan
    PASS fingerprint_changed | dda39a2011d5
    PASS version_unchanged | 0.3.0
    PASS no_page_errors

    34/34 PASS (task 32 AFTER)

## Regression: t31 — 22/22 PASS (re-run by task 32b)

Real AI2 dump `sn-1322321006870/20261124-092547` through base `:56627`
(seeded state) + mocks. Selection-aware helper updated (planWords filters
unchecked words); expectations extended, not weakened: the GPC word
0x00100201 matches exactly at row 305 but the last block-8 record (row
311) is 0x00160201 → `SUPERSEDED at row 311 — needs re-burn`, stays
selected, all 4 words still placed `["330+331","332+333","334+335",
"336+337"]`; queue equals proposed; fingerprint/version/mockfx display
assertions pass (`dda39a2011d5`, `0.3.0`). `22/22 PASS (AFTER)`.

## Regression: t27 22/22, t28 13/13, t30 20/20

t30 script unchanged from pw31 (`diff` empty) — 20/20 as recorded.

t27/t28 expectation updates (justified — the selection default is the
intended behaviour change, not a regression):

- t27: word 1 (0x00100201) is the LAST block-8 record (row 240) on the
  seeded card → now `ALREADY PRESENT (row 240) — no burn needed`, default
  UNchecked, excluded from proposed rows/queue by default. New assertions
  cover the old guarantee on the re-check path: ticking it names
  `row 242 → 0x00100201 + mirror row 243` with the
  `(record already present at row 240)` suffix and the queue carries the
  `already present — likely no-op (row 240)` tag.
- t27/t28 proposed-row expectations `242+243/236+237/238+239/244+245` →
  `236+237/238+239/241+242`: with the present word deselected only 3
  words are allocated, and the pre-existing per-block allocator places
  the block-8 word at the first blank pair after row 240 — 241+242 (odd
  start is legal for non-mirrored pairing here; same allocator, fewer
  entries). Not a placement-rule change; the old rows were the 4-word
  allocation.

## Environment / provenance

Servers started from /tmp/v32 (code at fingerprint dda39a2011d5):
`service --state-dir /tmp/v32_state --port 56627`,
`service --mock /tmp/newcard.json --port 56628`,
`service --mock /tmp/pw32/fixture-dump.json --port 56629`.
Suites in /tmp/pw32 (Playwright). All runs above executed 2026-11-24 by
task 32b; no hardware touched, no AI2 writes.
