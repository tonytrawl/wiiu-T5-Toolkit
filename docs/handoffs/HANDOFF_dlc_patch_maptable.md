# HANDOFF — DLC session: patch_mp/patch_zm mapsTable extension (console→console relink)

2026-07-10. Early release from the parked state: the pointer/allocation machinery this job
needs is proven (event walkers, runtime constants, loader_sim — 2-map anchor-validated), even
though the PC→console conversion gate is still closing its last class. This job is a
**console→console round-trip with one edit** — it does NOT depend on the PC conversion path.

## Goal
Relink genuine Wii U `patch_mp` and `patch_zm` with extended mapsTable rows so custom maps
(first target: mp_skate) are selectable, building on your established facts: menus list maps
from mp/zm mapsTable.csv; DLC gate @0x0241CBA0 (RPL patch surfaces DLC0+DLC1); row schema in
memory `wiiu-map-menu-registry`; `dlc0_load_mp.ff` loads on Cemu.

## FILE OWNERSHIP (hard — the assemble session is running)
READ-ONLY use of `native_linker`/`wiiu_ref` machinery (walker, loader_sim, wiiu_zone,
wiiu_ff, alloc_events). You may NOT edit any of it. Your code goes in NEW files (suggest
`dlc loading/native/patch_relink.py` etc.). If a walker gap needs a shared-file fix, write
it up and route through the main session. Never write under `E:\` — copy zones out first.

## Stage 1 — recon + walk (the unknown: patch zones are a new SHAPE)
Unlink both patch zones; walk to EOF with the console-side walker. Patch zones are menu/
table/script-heavy with no map assets — expect asset-type mixes the map zones never
exercised (menuDef unions were fixed for PC walks; console menus may surprise). Locate the
mapsTable csv asset(s), confirm the row schema against the registry findings, and record the
zone's asset inventory. If the walk desyncs, characterize precisely and STOP for routing —
do not hack shared walkers.

## Stage 2 — the gate: no-edit byte-exact round-trip
Re-emit each patch zone UNMODIFIED from the walked representation (the ReEmitter/round-trip
pattern) and require **byte-identical** output, then pack (0x7FC0 blocks) and Cemu-boot the
repacked-unmodified .ff as the deploy-path control (the dlc0 lesson: byte-identical input
isolates pack/deploy faults from content faults). No row edit lands before this gate passes
on BOTH zones.

## Stage 3 — the edit
Add the mp_skate row (mp first; zm row when a zm target exists) to mapsTable.csv. This is a
size-changing edit: every downstream pointer shifts — re-encode through the loader_sim
pointer model; re-walk the edited zone (self-consistency) before packing. Keep the edit
minimal (one row; no cosmetic reformatting). Then pack + sig-patch → Cemu: does the map
appear in the menu? (Selecting it will fail until the mp_skate .ff/.ipak exist — appearance
+ a load ATTEMPT of the right filename is the success signal; capture what it requests.)
Also confirm which DLC-gate tier governs the new row — the RPL patch surfaces DLC0+DLC1
only; a non-appearing row may be gate, not table.

## Definition of done
Both patch zones: walk to EOF + byte-exact no-edit round-trip + repacked-unmodified boots.
patch_mp with the mp_skate row boots, row visible in the menu, engine requests the expected
zone name (recorded). Findings doc with the row schema as-built and any walker gaps routed
to the main session. This doubles as the linker's second end-to-end proof on a non-map zone.
