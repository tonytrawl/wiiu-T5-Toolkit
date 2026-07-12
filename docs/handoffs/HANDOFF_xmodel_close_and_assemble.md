# HANDOFF — close XModel (skinned emit-rigid) → build the no-backbone assemble loop

Standalone continuation doc for the XModel/assemble session. Two steps to the **first no-backbone
mp_skate artifact**: (1) close XModel with skinned emit-rigid, (2) build the assemble loop. All known
caveats are catalogued in **`CAVEATS_nobackbone_boot.md`** — read it; it defines how to interpret the
first boot.

## Where XModel stands (this session's landing)
- collmaps chain (`convert_xmodel_collmaps`): span-mismatch **0/459 mp_skate, 0/437 raid**, 0 exceptions.
  (Trap fixed: FOLLOW cbrushside carries an inline `cplane_s(20)` after the sides array.)
- inline-material GX2 images (`convert_image` wired into `convert_material`): PC 80B GfxImage + loadDef
  pixels → console 328B GX2 body + name + tiled pixels, via the validated `ipak_stream` path (no new
  tiling). Streamed images (`resourceSize=0`) emit a console streaming body (pixels from the map ipak).
- **Every non-skinned XModel emits a stream-valid console body: raid 437/437, mp_skate 459/459.**
- **The bar is self-consistency, not genuine byte-parity** (re-walk emitted bytes → parser consumes
  exactly the emitted length). See CAVEATS §governing-principle.
- Measured: **mp_skate has 7 skinned XModels** (not 0).

## STEP 1 — close XModel: skinned emit-rigid (small; do first — it's a prerequisite)
The assemble emits all 466 mp_skate XModel bodies in stream order; the 7 skinned must be stream-valid
or the loop breaks on them. Emit-rigid **is** the stub the assemble needs, so this closes XModel *and*
unblocks a clean assemble in one step.
- **Emit as a GENUINE rigid surface: clear `flags&2`**, omit vertsBlend + the 3 Latte skin-streams,
  emit the stored bind-pose verts. Do NOT leave the skinned flag set with streams absent (the loader
  may fault expecting stream data). Flag-cleared rigid = stream-valid + load-safe. (CAVEATS §1.)
- **Validate:** the 7 skinned models now emit stream-valid bodies (self-consistent re-walk) → mp_skate
  **466/466** XModels stream-valid.
- **Also do the cheap classification:** identify what the 7 skinned models are (ambient prop vs animated).
  If all ambient, note in CAVEATS §1 that emit-rigid is *permanent* for mp_skate (frozen bind pose is
  invisible for static props). Real skin-stream synthesis stays a **zombies-tier** item
  (`HANDOFF_skinned_skinstream.md`), not owed to the MP path.
- **Loader-tolerance question folds into the first boot** — no separate test; if the boot accepts the
  flag-cleared rigid models, loading is settled.

## STEP 2 — the no-backbone assemble loop (`produce_nobackbone.py`)
Emit a complete console zone from PC alone. Design (raid-oracle control + fatal asserts):
1. **Author the container:** console asset list (order + type remap — validated 2 MP maps; MP inserts =
   MAP_ENTS + duplicate SOUND) via `_assetlist_author.py`; reuse the PC string table verbatim (identical
   PC↔console).
2. **Body-emission loop** in authored order: dispatch each asset to its converter —
   `pc_to_console.PCConverter` (simple/world), `material_convert` (+inline images), `techset_translate`
   (substitution), `xmodel_convert` (now incl. rigid-skinned), `fx_convert`, GfxWorld via the region
   generators/stubs (Track F split), **valid-shaped stubs** for smodelDrawInsts + MAP_ENTS.
3. **Omap finalize with a FATAL assert:** every fixup must resolve to an emitted region;
   `PCConverter.finalize` returns the unresolved count — make it fatal. (Dangling alias = load crash.)
4. **Instrument:** per-asset log (index, type, emitted size, fixup count); assert block-5 offsets
   monotonic and emit order == authored list.
5. **Offline container round-trip:** run `wiiu_zone` back over the output; catch structural bugs before
   packing.
6. **Pack + sig-patch → `mp_skate_wiiu.ff` → Cemu.**

### Raid-oracle control FIRST (the guard)
Run the loop on **raid** before the blind mp_skate run. Diff the assembled output against genuine raid
with a **known-exception allowlist** (material's 9 hashIndex, substituted techsets, the −16/−32 class,
skinned) — diffs **only** in allowlisted assets = machinery proven; any diff **outside** = an assemble
bug caught on a checkable map. Raid must also stay end-to-end.

## Prerequisites still open (from other sessions — coordinate, don't duplicate)
- **GfxWorld region generators (Track F):** the no-backbone GfxWorld emit (smodelDrawInsts converter +
  GX2 routing + ~90 KB novel synthesis). The assemble uses these; for a first artifact, stubs per the
  established split are acceptable where a generator isn't ready. Coordinate with that session.
- Anything editing `pc_walk.py` (e.g. the WEAPON session) — **one editor at a time**; the assemble reads
  it. mp_skate has 0 weapons so WEAPON doesn't gate this artifact.

## First-boot expectation (read CAVEATS §9)
Cemu does **not** capture `OSReport` for this build → a failure gives a **symbolized stack, not a
message.** So the offline asserts (omap-finalize, container round-trip, self-consistency) are your
primary debugging surface; symbolize any crashlog with `wiiu_ref/rpl_symbolize.py`. Treat the first
artifact as a **diagnostic** — it names the next constraint. Interpret its outcome against
`CAVEATS_nobackbone_boot.md` §"How to read the first boot".

## Files
`native_linker/xmodel_convert.py` (rigid-skinned emit), `native_linker/produce_nobackbone.py`
(assemble loop), `native_linker/_assetlist_author.py`, the converters (`material_convert`,
`techset_translate`, `fx_convert`, `pc_to_console`), `wiiu_ref/wiiu_zone.py` (round-trip),
`WiiU_FF_Studio/wiiu_ff.py` (pack), `wiiu_ref/rpl_sigpatch.py` + `rpl_symbolize.py`. Never write under
`E:\`. Reference: `CAVEATS_nobackbone_boot.md`, `PROJECT_STATE.md`.

## Definition of done (this handoff)
mp_skate XModels 466/466 stream-valid (incl. 7 rigid-skinned); the assemble loop produces
`mp_skate_wiiu.ff` (raid-oracle control passes with only allowlisted diffs); first Cemu boot attempted
and its outcome recorded against the caveats. That is the **first no-backbone artifact** — the milestone.
