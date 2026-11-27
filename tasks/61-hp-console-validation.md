# TASK 61 — Validate the HP fuse console against the live card AND audit its proposed burns + order vs the GPU2 ground truth

Zero-context builder agent; everything you need is here.

## Mission
Three validations, one evidence file:
1. **Live validation**: is the console at `http://192.168.0.175:8790` correctly reporting the currently plugged-in card (CMP 170HX, serial …9272, BDF 0000:03:00.0)?
2. **Proposal validation**: audit the console's PROPOSED burn set for this card — every record, every value.
3. **Order validation**: audit the ORDER of the proposed burns against the proven razk-batch2 order precedent and the console's own placement rules.

## Read FIRST (ground truth, do not re-derive)
- `/home/raza/nvidia/pico-ga100vfi/evidence/60-gpu2-burn-truth.md` — the HP card …9272 is **NEVER BURNED** (stock: factory FF ends row 300, blank 301–487, IFF start 488, DEVIDA 0x20C2). Its defect map: GPC_DIS 0x13, **TPC_GPC4_DEF 0x01** (GPC4·TPC0 dead — must STAY masked), FBP_DEF 0x840, FBPA/FBIO_DEF 0xC03000; potential 126 SM / 80 GB. razk-batch2 is NOT portable to it. razk order rule: column fuses first (6/7→48/49→2/3), FF ascending, IFF macro rows last; every FF record two-step (inert chain=0 row, then chain-armed row).
- `/home/raza/.hermes/skills/hardware-optimization/ga100-fuse-burn-plan/references/gpu2-hp-burn-truth.md` — same facts, skill form.
- Console source (LOCAL, authoritative): `/home/raza/nvidia/pico-ga100vfi/host/ga100vfi/console/service.py` (~4000 lines — grep -n then sed ranges ≤60 lines; grep `proposal`, `burn_preview`, `FF_FIELDS`, `_ff_plane_gate`, `placement`, `IFF_RECORD`, `two_layout`).

## Access
- Console HTTP: from THIS machine directly `http://192.168.0.175:8790` (console binds 0.0.0.0). Use `curl -s` locally.
- HP host for file reads only: `sshpass -p 'khankhan' ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no administrator@192.168.0.175 '<cmd>'` (no curl on HP; pipe outputs through head).
- HARD RULES: NO POST to `/api/burn`, `/api/glitch/start`, `/api/glitch/stop`, or anything that writes. GETs everywhere are fine. POST `/api/preview` (or whatever the preview endpoint is — grep the routes in service.py first) is allowed ONLY after you verify in the source that the preview path performs no latching writes (cite the line). The card's link is degraded to Gen1 and its config space was flaky after Nov-26 glitch shots — if BAR0 reads fail or return 0xffffffff, that is the CARD's state, not a console bug: record it and fall back to validating the proposal engine against the Nov-26 dump file on the HP (`/home/administrator/nvidia/GPU2/dump_9272_20261126T113515Z.bin`, scp it down; the parser from task 60 is at `/tmp/gpu2/parse.py`).

## Deliverables (evidence LOCAL: /home/raza/nvidia/pico-ga100vfi/evidence/61-hp-console-validation.md, append incrementally)
1. **Live state table**: GET /api/live + /api/gpus + /api/glitch/status — driver-unbound detection, GFW_BOOT/FEAT_READOUT readouts populated or empty (and why), link speed, Goldilocks state, never_write list present. Mark each row CORRECT / WRONG / DEGRADED-BY-CARD-STATE with the raw values.
2. **Proposal audit**: get the console's proposal for this card (find the proposal endpoint in service.py routes; GET it). For EVERY proposed record: row, value, decoded feature — check against (a) the card's OWN defect map (from the Nov-26 dump: does the proposal keep GPC4·TPC0 masked? does it start FF at 301+, not 326? does it respect IFF start −1?), (b) the razk-batch2 record set as the proven shape (which features present/absent and why that's right for a stock card), (c) the console's own plane gate + bit5 rule. Verdict per record: SAFE / RISKY / WRONG + one-line reason.
3. **Order audit**: does the console's proposed/queued order follow the proven discipline — column fuses before FF? FF ascending? IFF/SS rows last? two-step inert-then-armed per record (does the console do two-step or single-step burns — check the burn_execute path in source)? shared 16-bit words (e.g. off8, off12, off23) written once with final value or last-write-wins ordered? Compare against razk-batch2's order (evidence 60 §3) and flag every deviation as OK-with-reason or DEFECT.
4. **Cross-check the console's decode** of the Nov-26 dump (upload via the console's dump-load path if it has one GET-side, or run the preview "from dump row" path read-only) against task 60's parse — same rows occupied, same block-8 winner 0xF89E0201, same DEVIDA 0x20C2.
5. **Verdict summary**: top-line — can this console be trusted to plan (not yet burn) this card? List any console defects found, ranked.

## Hard rules
- READ-ONLY on HP (ssh reads + GETs; the one allowed POST is the verified read-only preview).
- Do NOT modify service.py/gui.py; defects get reported, not fixed.
- Context discipline: grep -n then sed ranges ≤60 lines on service.py; never re-read a captured region; evidence appended incrementally.
- Finish: print `TASK61_DONE` + 10-line summary (must state: live-state verdict, N proposed records with SAFE/RISKY/WRONG counts, order verdict, top defect if any).
