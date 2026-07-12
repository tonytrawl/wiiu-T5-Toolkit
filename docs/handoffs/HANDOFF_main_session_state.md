# HANDOFF → MAIN SESSION: current project state (fill-in only, nothing to implement)

Date: 2026-07-05. Read this to get oriented. **Everything below is already DONE and in
the tree / installed / in memory. You do NOT need to implement any of it.** Your job is
to hold the map, coordinate the sub-sessions, and hand out the task blocks in
`TASKS_new_sessions.md`. Do not redo finished work.

Project: reverse-engineer BO2 (T6) Wii U fastfiles to port PC (and 360) maps/DLC to Wii U.

## Where we are in one line
The PC→Wii U **load pipeline is solved and hardware-confirmed** — a converted `mp_raid`
DB-loads 100% clean on Wii U. The only remaining wall is **rendering** (null GX2 shaders →
black screen), and the direction for that is committed (Branch B: inline real extracted
GX2 shaders). Sound-bank conversion is solved. Signature is bypassed.

## What is DONE (do not re-implement)
1. **RSA signature bypass — CONFIRMED WORKING.** Custom/repacked/zeroed-sig `.ff` files load
   to the map. (Synopsis below — this was NOT in the older Track-A handoff.)
2. **Codec block-size fix.** `wiiu_ff.py` packs genuine 40-byte header + 0x7FC0 blocks;
   required or repacks crash later. (memory: `wiiu-codec-blocksize`.)
3. **All fastfile struct/pointer/block load crashes SOLVED** (skinnedverts, gameworldmp,
   clipmap/mapEnts, block layout incl. RUNTIME_PHYSICAL default, image IPAK streaming).
   `mp_raid` DB-loads clean on hardware. (memory: `track-a-ipak-streaming`; source changes
   already compiled into `tools/ref_oat` Unlinker.)
4. **PC inline-texture → IPAK streaming** (Track A) implemented; OOM gone.
5. **Sound banks:** PC `.sabs/.sabl` → Wii U solved (`WiiU_FF_Studio/sab_convert.py`,
   memory `wiiu-sab-converter`).
6. **Studio GUI "Batch Convert" tab** + `WiiU_FF_Studio/batch_convert.py`: drag/multi-select
   mixed `.ff` / `.sabs` / `.sabl` / `.ipak`, output folder, original names kept. `.ff` and
   sound banks wired; `.ipak` auto-wires when a converter fn lands in `wiiu_ref/ipak.py`.
7. **Map-menu registry research** (how to add a custom map to MP/Zombies lists): memory
   `wiiu-map-menu-registry` — `mp/zm mapsTable.csv` + DLC gate `Content_PlayerHasDLCForMapPackIndex`
   @0x0241CBA0.
8. **Signature-bypass tooling persisted:** `wiiu_ref/rpl_sigpatch.py` (+ `wiiu_ref/sig_bypass/`
   archived pristine & patched update RPLs). Reproduces the installed working RPLs byte-exact.

## RSA signature-bypass — synopsis (was missing from the shader handoff)
- **What it does:** disables the fastfile RSA signature check in the engine RPLs so
  custom/repacked `.ff` load without a valid signature. Unblocks the whole pipeline.
- **Where:** `__DBX_AuthLoad_ValidateSignature_Try` (db_auth.cpp) — returns 1 on valid sig
  (ORs a 0x80 "validated" flag), 0 on fail, via LibTomCrypt RSA.
- **Patch (1 instruction):** replace the `bl DB_SetPublicKey` inside it with a branch to its
  own success block — skips SetPublicKey + all RSA, always returns valid; state ptrs already
  set up so nothing downstream breaks.
- **Two gotchas (resolved):** (a) patch the SHARED engine RPL `t6_cafef_rpl.rpl` (loaded
  first, own db_auth copy) AND `t6mp_cafef_rpl.rpl`. (b) Cemu/CFW load RPL CODE from the
  **UPDATE partition** (`…\Cemu\mlc01\usr\title\0005000e\1010cf00\code\`), a different/smaller
  build with its own addresses — editing the base/E:\ RPLs did nothing. Content still comes
  from E:\…\content (so FF edits worked but code edits initially didn't).
- **Delivery:** directly-patched update RPLs, installed with `.orig` backups. Hardware: same
  on CFW, or an Aroma runtime memory-patch plugin. **Status: CONFIRMED WORKING.**
- Exact VAs per build (base/MP/update differ) + the reproducible tool: memory `wiiu-sig-bypass`
  and `wiiu_ref/rpl_sigpatch.py`.

## The one open wall (NOT yet solved) — rendering / GX2 shaders
Post-load **black screen = null GX2 pass shaders** (D3D11 shaders don't transcode to GX2; the
writer emits null pass shaders). Reference-remap (rename to `,name` stub → loader swap from
common_mp) was tested and **CRASHED (SELFREF)** → proven the loader does NOT resolve techset
references on Wii U. **Committed direction: Branch B — inline real extracted GX2 shaders** from
a genuine Wii U zone. Needs the genuine-zone VIRTUAL-block walker (`techset_extract.py`) finished
(currently 5/229 + 55 refs; fails on block-5 alias resolution). Full detail:
`HANDOFF_trackA_shaders_v2.md` + memory `track-a-ipak-streaming`.

## Key paths (all current)
- Unlinker (newest): `tools/ref_oat/build/bin/Release_x64/Unlinker.exe`
- Codec/pack + GUI: `WiiU_FF_Studio/` (`wiiu_ff.py`, `sab_convert.py`, `batch_convert.py`, `wiiu_ff_studio.py`)
- RE tools: `wiiu_ref/` (`ipak.py`, `ipak_stream.py`, `gx2_texture.py`, `rpl_sigpatch.py`, `techset_extract.py`)
- capstone Python: `C:/Users/Tony - Main Rig/AppData/Local/Programs/Python/Python313/python.exe`
- Cemu content slot: `E:\Wii U Black ops 2\content\english\mp_raid.ff` (+ `content\mp_raid.ipak`)
- Patched RPLs (installed): `…\Cemu\mlc01\usr\title\0005000e\1010cf00\code\` (.orig backups kept)
- Cemu log: `C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\log.txt` (FS-API only; mp_raid handle
  `3080289`, ~105 reads = full load; does NOT show GPU/shaders).

## Memory index (all written)
`wiiu-sig-bypass`, `wiiu-codec-blocksize`, `track-a-ipak-streaming`, `wiiu-sab-converter`,
`wiiu-map-menu-registry`, `wiiu-native-unlinker`, `wiiu-geometry-format`, `bo2-wiiu-fastfile`.
