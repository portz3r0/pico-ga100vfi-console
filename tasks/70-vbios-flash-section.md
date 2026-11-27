# TASK 70 — VBIOS flash section in the console (owner: "add the bios flash option as well")

Repo `/home/raza/nvidia/pico-ga100vfi`, main (pull latest — tasks 68/69 changed gui.py+service.py before you). Console: `host/ga100vfi/console/service.py` + `gui.py`. Bench HP has stock `nvflash` installed (owner-confirmed) and the target ROM at `/home/administrator/nvidia/A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi.rom`.

## Feature
A "VBIOS flash" card in the console (place it after the Burn queue card) that owns the post-DEVID flash phase end-to-end:

1. **ROM picker = FILE PICKER POPUP (owner correction)**: clicking "Choose ROM..." opens a modal file browser backed by `GET /api/vbios/browse?dir=<path>` (server lists subdirs + *.rom files with size+md5; default dir `/home/administrator/nvidia`, CFG key `rom_dir`; allow navigating within the filesystem). Selected path + size + md5 shown on the card after pick. No dropdown.
2. **Backup first, always**: "Save current VBIOS" runs `nvflash --save <file>`; auto-invoked as step 1 of the flash action too. Backup goes to `<state_dir>/vbios-backups/<serial>-<stamp>.rom`, verified non-empty and not all-00/FF, then reported with md5. Flash REFUSES if backup save/verify fails.
3. **Flash action** "Flash selected ROM": confirm dialog (irreversible-ish, board-id mismatch expected) → server runs `nvflash -4 -5 <rom>` (auto-answer prompts with 'y' on stdin; capture full output; timeout 120 s). **NO --protectoff by default (owner correction: not required)** — provide an optional checkbox "run nvflash --protectoff first" that prepends it when ticked. Journal each step to the existing burn journal (event types vbios_backup / vbios_flash, fsync'd before the command runs — same discipline as fuse writes).
4. **State awareness (owner corrections)**: nvflash requires the **nvidia kernel MODULES UNLOADED** (nvidia, nvidia_uvm, nvidia_modeset, nvidia_drm — not merely unbound from the device). Guard checks module load state (the existing /api/driver data reports lsmod): refuse flash while ANY nvidia module is loaded, one-line reason + **"Unload nvidia modules"** button (reuses /api/driver/op unload; show its output). Also refuse while a glitch campaign is running. Warn (don't refuse) when burn queue non-empty. Bench note for evidence: on the HP, rmmod has previously hung in D-state when the card link is degraded — if unload fails, surface the exact stuck module and advise cold boot, don't retry-loop.
5. **Post-flash verify**: after flash completes, show `lspci -n -s <bdf>` + `nvidia-smi --query-gpu=name,memory.total --format=csv` output (best-effort; card may need cold boot to attach — say so in the note, don't treat absence as failure).

## API (service.py)
- `GET /api/vbios/list` → roms[{path,size,md5}] + backups[{name,md5,when}] + driver state summary.
- `POST /api/vbios/backup` → {ok, path, md5} or precise error.
- `GET /api/vbios/browse?dir=<path>` → {dir, parent, dirs:[], roms:[{name,path,size,md5}]} (path-traversal-safe, roms only *.rom).
- `POST /api/vbios/flash` {rom, confirm:true, protectoff:bool} → runs backup-if-not-fresh (<24 h old backup for this serial counts as fresh), optional protectoff, flash; returns {ok, output_tail, backup:{path,md5}} . Guard: campaign not running, driver NOT bound, rom exists, confirm true. Mock mode: canned outputs, no subprocess.
- **nvflash is VENDORED in the repo (owner requirement)**: copy the working Linux binary from the HP (`which nvflash` → scp to local repo) into `host/bin/nvflash`, chmod +x, commit (binary blob is fine). Resolution order for the console: repo `host/bin/nvflash` (default) → CFG `nvflash_path` override → system PATH. Record the binary's version output (`nvflash --version`) and md5 in the task evidence. If the HP binary is a symlink/wrapper, vendor the real ELF.

## Tests (unittest, NOT pytest; baseline FAIL-set must stay identical: test_burn_window/test_program_sequence/test_verify6 TypeError, test_verify8 KeyError, test_task17 8/13)
- `host/tests/test_vbios.py`: mock-mode list/browse/backup/flash happy paths; refusal without confirm; refusal while campaign running; refusal when ANY nvidia module is loaded (owner correction: nvflash needs modules unloaded, not just device unbound); protectoff checkbox prepends the command; backup verification rejects all-FF content; journal events written before commands (monkeypatch subprocess to assert ordering); vendored binary exists + executable + md5 recorded.
- py_compile, node --check on extracted JS, tests/test_allspark_frontend.py still passes.

## Deploy to HP + verify
Standard: sshpass pw khankhan; sudo `echo khankhan | sudo -S bash -c`; root-owned clone via /tmp; restart backgrounded (`sudo bash -c 'systemctl restart ga100-fuse-console &'`), poll /api/gpus. NOTE the bench host may be mid-hang/cold-boot — if ssh or the API is unreachable after 3 tries, commit anyway and report deploy as PENDING (do not fight the host). GETs only; do NOT POST /api/vbios/flash on the live bench (owner will test it).
Verify served page contains "VBIOS flash" + rom picker markers; md5 parity.

## Finish
Commit on main (no push), TASKS.md line, marker TASK70_DONE + 8-line summary.

## Rules
- stdlib only. subprocess with explicit argv lists (no shell=True). Never run nvflash in mock mode.
- Do not weaken fuse-side gates; this is a new phase living beside them.
