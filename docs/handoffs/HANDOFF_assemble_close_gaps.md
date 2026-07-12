# HANDOFF — ASSEMBLE session: close the named gaps → first mp_skate artifact

Standalone continuation doc for the assemble session (supersedes
`HANDOFF_xmodel_close_and_assemble.md`, whose two steps are DONE). You own
`native_linker/produce_nobackbone.py`. Goal of this handoff: drive the assemble loop from
27.3 MB / 495 assets to a **complete, raid-oracle-gated `mp_skate_wiiu.ff`**.

## STEP 0 — pull shared-file edits FIRST (do not skip)
The WEAPON session edited shared files you import: `pc_walk.py`, `walker.py`, `struct_layout.py`,
`material_convert.py`, `clipmap_pc.py`. Sync/pull those before your next run and re-run your
last-known-good assemble to confirm no regression (same 495-asset output). One editor at a time on
those files from here on — you are now the editor of record for the assemble path; coordinate
before touching them if another session is active.

## Where you left off
- XModel fully closed: mp_skate **466/466** stream-valid (incl. 7 emit-rigid skinned — permanent
  for MP, they're ambient props + the dog); raid 440/440.
- `assemble_zone` RUNS end-to-end and emits 27.3 MB / 495 assets, with every remaining gap named:

| Gap | Count | Approach (approved) |
|---|---|---|
| Techsets | ×245 | **Wiring only.** Track B corpus + manifest exist (`native_linker/techset_translate.py`, `mp_skate_subst.json`, 0 unresolved). Dispatch TECHSET → substitution blob. |
| FX | ×79 | Header converter done (388/388 byte-exact); elems are layout-identical — wire `fx_convert` through. |
| SndBank | ×1 (49.8 MB) | **Try byte-copy first** (PC↔WiiU SndBank measured byte-identical). Only treat as RE if the copy fails re-walk/oracle. |
| XAnim + smalls | ×7 + misc | Convert per existing per-type rules; these are small — chase to root if any resyncs drift. |
| GfxWorld | ×1 | Track F owns the region generators (`gfxworld_*.py`); you CALL them. Where a generator isn't ready, use the agreed valid-shaped stubs (smodelDrawInsts stub = base world without props — acceptable for artifact #1). |

Order: **techsets → FX → SndBank byte-copy → XAnim+smalls → GfxWorld (generators/stubs)**.

## THE GATE — raid-oracle control (do not let mp_skate boot before this passes)
KEY RISK: omap `interior_approx=2613`. Self-consistency validates SIZES, not POINTER VALUES — a
wrong interior target is a silent dangling pointer that self-consistency cannot see.

1. Run the full assemble on **raid** (genuine console oracle exists).
2. Byte-diff assembled raid vs genuine raid with the known-exception **allowlist**: material
   hashIndex ×9, substituted techsets, the −16/−32 class, skinned emit-rigid.
3. **PASS = diffs only in allowlisted assets.** Any diff outside the allowlist is an assemble bug —
   fix it on raid where you can see it, not on blind mp_skate.
4. `PCConverter.finalize` unresolved count: currently **1178 → must reach 0**, then make it FATAL.

Two bars, never conflate: raid gets byte-exact-vs-oracle; mp_skate gets self-consistency +
the raid-proven machinery. Never chase genuine byte-parity on mp_skate — impossible by design.

## What a first mp_skate CONVERSION ATTEMPT needs (the full checklist)
1. All five gap rows above closed (stubs acceptable only where marked).
2. Raid-oracle control PASS + unresolved=0 fatal assert armed.
3. **Offline verification before packing:** re-walk the emitted zone (`wiiu_zone` round-trip) —
   parser consumes exactly the emitted length; block-5 offsets monotonic; emit order == authored
   asset list (MP inserts = MAP_ENTS + duplicate SOUND; stubs fine for boot #1).
4. **Pack:** console zone → v148 .ff via `WiiU_FF_Studio/wiiu_ff.py` (genuine 0x7FC0 blocks).
5. **Ipak:** author the mp_skate .ipak from PC sources via the existing pipeline
   (base+mp+**dlc1** auto-select — validated path; byte-exact machinery).
6. **Sig-patch:** zeroed-sig repack loads only under the patched update-partition RPLs
   (`wiiu_ref/rpl_sigpatch.py` or the GUI tool) — confirm the user's Cemu setup has them.
7. Deploy .ff + .ipak → user boots in Cemu. **Menu registration is NOT needed for boot #1** — the
   map can be launched via console/exec; mapsTable wiring is the DLC session's tier.

## How to read the first boot
The first artifact is a **diagnostic, not a finish line** — interpret against
`CAVEATS_nobackbone_boot.md` §"How to read the first boot". Cemu does not capture OSReport: a
failure gives a symbolized stack only (`wiiu_ref/rpl_symbolize.py`), no message. Your offline
asserts (omap-fatal, round-trip, self-consistency, raid control) are the real debugging surface —
invest there, not in boot-loop guessing.

## Constraints (standing)
- NEVER write under `E:\` (installed game). Copy out first.
- struct_layout is WRONG for GfxWorld draw-onward + several console sizes — trust probes/pins.
- Raid-luck-masking is the house pattern: a rule validated only on raid is not validated.
- Keep `PROJECT_STATE.md` + `CAVEATS_nobackbone_boot.md` truthful as each gap closes.

## Definition of done
Raid-oracle control passes with only allowlisted diffs; unresolved=0 fatal; mp_skate assembles
complete (all 5 gaps closed or agreed-stubbed), round-trips offline, packs, and ships as
`mp_skate_wiiu.ff` + ipak ready for the user's Cemu boot, with the outcome recorded against the
caveats register.
