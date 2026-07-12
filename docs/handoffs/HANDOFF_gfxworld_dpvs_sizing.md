# HANDOFF → geometry session: make gfxworld_probe2 PC DPVS sizing data-driven

Focused, cold-startable task. **One fix, four payoffs.** `gfxworld_probe2`'s PC-side GfxWorld walk
completes correctly on raid but lands EARLY (a false end) on every other map, because its DPVS
sub-array sizing was tuned on raid and doesn't generalize. Making that sizing **data-driven** (read
each array's count from the map's own GfxWorldDpvs headers instead of raid-derived `CFG['pc']`
constants) is now the single highest-leverage action across the whole effort.

## Why this is the critical fix right now
The PC map-zone walk (Track E) reaches **end-of-zone on raid** and, after this session's fixes,
walks all three acceptance maps cleanly **up to GfxWorld** — then all three drift at *exactly*
GfxWorld. Landing this fix simultaneously:
1. **Completes Track E** — all maps walk to end-of-zone (the acceptance gate).
2. **Resolves GfxWorld localization** for any map (this IS that blocker, now pinned to one function).
3. **Unblocks no-backbone assemble** — a novel map's GfxWorld becomes natively readable.
4. **Finalizes Track B's enumeration number** — the last few techsets sit past the current drift point.

## Exact diagnosis (precisely characterized by Track E)
- All three acceptance maps drift at GfxWorld: **nuketown @asset 624, mp_skate @800, zm_nuked @1020.**
- probe2's PC GfxWorld walk **completes but lands early** — a *false end* inside GfxWorld. The real
  GfxWorld extends PAST it; the first unconsumed bytes are an **inline material `lightmap1_secondary`**
  (i.e. the walk ended before consuming GfxWorld's tail inline data).
- Root cause: the **DPVS sub-arrays are mis-sized on non-raid maps.** On nuketown the probe finds
  (matched / expected):
  - `surfaces` (matAliasOK) **16 / 137**
  - `smodelInsts` **14 / 81**
  - `smodelDrawInsts` **5 / 70**
  — all *healthy* (near-full) on raid. So `CFG['pc']`'s DPVS sizing reflects raid's counts and is wrong
  for other maps, which truncates/misaligns the sub-array walk and produces the early false end.
- **Corrected false lead:** the earlier "2.7 MB / 0x4805620 GWMP" reading was a garbage false-positive
  — ignore it; the real issue is the DPVS sub-array counts above.

## The fix
Make the PC DPVS sub-array sizing **read the actual element counts from each map's own GfxWorld body /
DPVS headers**, not from `CFG['pc']` constants:
- The counts live in `GfxWorldDpvsStatic` / `GfxWorldDpvsDynamic` (e.g. `surfaceCount`,
  `staticSurfaceCount`, `smodelCount`, `smodelDrawInstCount`, etc. — the fields that drive
  `surfaces` / `smodelInsts` / `smodelDrawInsts`). probe2 already walks the GfxWorld body to reach
  DPVS; read those count fields there and size each sub-array from them.
- Replace every raid-tuned size/count constant in the PC GfxWorld path with the value read from the
  current map's headers. The 16/137, 14/81, 5/70 mismatch is the signature that a hardcoded count is
  in play — chase each to the header field it should come from.
- After the sub-arrays, the walk must consume GfxWorld's **tail inline data** (the `lightmap1_secondary`
  material and whatever follows) so it lands on the asset *after* GfxWorld, not the false end.

## Validation (don't call it done until all pass)
1. **Raid must not regress** — the data-driven sizing must reproduce raid's currently-working numbers
   (raid's counts are near-full, so reading them from headers should match the old constants).
2. probe2's PC GfxWorld walk **consumes the full GfxWorld** (lands on the next asset) on **raid +
   nuketown + mp_skate + zm_nuked**.
3. Hand back to Track E: `pc_walk` reaches **end-of-zone on all three acceptance maps** (nuketown,
   mp_skate, zm_nuked), zm weighted heaviest.

## Scope / ownership / traps
- This lives in **`wiiu_ref/gfxworld_probe2.py`** (`CFG['pc']` + the DPVS sub-array walk) — the geometry
  session owns it; Track E consumes it read-only, so the fix belongs here.
- struct_layout is WRONG for GfxWorld `draw` onward — use the probe2 landmark offsets (body 1076
  console / 1028 PC), never struct_layout, for anything past the head.
- This is the SAME class of bug as the four raid-alignment/sizing-luck issues found today (asset-list
  4-align, GfxImage baseSize offset, XAnim `parse_delta` align, now DPVS sizing): a raid-happened-to-fit
  constant that fails on other maps. The fix pattern is identical — replace the raid constant with the
  data-driven value.
- Don't edit under `E:\`.

## Files
`wiiu_ref/gfxworld_probe2.py` (the fix), and the GfxWorldDpvsStatic/Dynamic layout for the count
fields. Track E's `native_linker/pc_walk.py` is the consumer that proves end-of-zone once this lands.
