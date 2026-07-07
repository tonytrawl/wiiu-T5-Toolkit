# FINDINGS — GfxWorld PC-walk generalization drift (corrects the "DPVS sizing" handoff)

Date 2026-07-07. Investigating the handoff "make gfxworld_probe2 PC DPVS sizing data-driven."

## ✅ GfxWorld FULLY DONE (2026-07-07) — four raid-masked bugs, all found via OAT load-order diff
1. **skyBoxModel XString @body+36** (see below) — the first, biggest drift.
2. **Tail offsets off-by-4 + missing arrays.** PC `occl_off` was 988 (should be 992 = occluders PTR);
   raid's empty tail masked it. Added `outdoorBounds` (numOutdoorBounds×24 @OCC+4/+8) and `waterBuffers[2]`
   (@body+956, buffer data if FOLLOWING). Tail order (OAT): waterBuffers, water/corona/rope/lutMaterial,
   occluders, outdoorBounds, heroLights(56), heroLightTree(32).
3. **INSERT (-2) tail materials are INLINE.** `lutMaterial@984 = 0xFFFFFFFE` (INSERT): OAT LoadPtr_Material
   loads inline for BOTH FOLLOWING(-1) and INSERT(-2) — INSERT also registers it as a listed asset.
   Consume on `in PTRS`, not FOLLOW-only.
4. **INSERT techniqueSet is an INLINE techset.** That inline material's `techniqueSet@92 = INSERT` →
   OAT LoadPtr_MaterialTechniqueSet loads the techset inline for FOLLOWING *and* INSERT. Replaced the old
   `raise 'inline PC techset'` guard with a real inline-techset consumer (`_pc_techset_span` →
   native_linker/techset_pc). All four are the same raid-degenerate-masking pattern.

Result: `pc_walk` now walks GfxWorld+GameWorldMp+trailing-techsets clean on all maps.

## ✅ mp_skate WALKS END-TO-END (840 assets) — additional Track E dispatcher fixes (2026-07-07)
6. **clipMap DynEntityDef inline physPreset.** `native_linker/clipmap_probe.py` skipped per-def inline
   sub-assets. Added per-def loop (OAT Load_DynEntityDef order: xModel@32/destroyedxModel@36/destroyFx@44/
   destroyPieces@52/physPreset@56). physPreset span = 84 body + name str + sndAliasPrefix str. (2 defs on
   mp_skate.) Guards raise for xModel/destroyFx inline (need dedicated consumers; absent on mp_skate).
   → mp_skate 805 → END (840). Note: pose/client/server/coll lists ARE RUNTIME (0 file bytes) — correct.
7. **FX FxElemDef extended `unknownDef`.** `native_linker/fx_pc.py`: for elemType not TRAIL/SPOT_LIGHT
   (e.g. type 0 SPRITE_BILLBOARD), extended = single char (OAT `Load<char>`), not an error. `else: c.skip(1)`.
8. **FX FxTrailDef offsets off-by-4.** vertCount@12 verts@16 indCount@20 inds@24 (FxTrailVertex=20).
   → zm_nuked 1061 → 1153.

## Acceptance status (2026-07-07)
- **mp_skate: END-TO-END ✅** (840). **raid: END-TO-END ✅** (no regression).
- zm_nuked: 1061→1153, now XANIMPARTS@1154. nuketown: XANIMPARTS@801. zm_transit: WEAPON@505 (no consumer).
- **Remaining blocker = WEAPON (universal, all 3 maps).** XAnim trace-back COMPLETE: nuketown's
  XANIMPARTS@801 drift is a downstream symptom — asset 788 is a `WEAPON` (root=None → skipped, 0 bytes),
  which desyncs everything after into a default/zero region that false-resyncs on next=0. XAnim
  offsets/enum are all correct vs OAT (not a field bug). Inline-WEAPON counts (hp=FOLLOW, no consumer):
  nuketown 1, zm_nuked 98 WEAPON + 31 WEAPON_CAMO, zm_transit 107 WEAPON + 29 WEAPON_CAMO. mp_skate has
  ZERO (weapons aliased from common_mp) — that's why it walks end-to-end. So WEAPON is NOT zombies-specific;
  it blocks nuketown (MP) too and is the single gate for the remaining acceptance maps.
  **Scope:** WeaponVariantDef load db = 2033 lines, ~200 loads, nested Loaders (XModel, Material,
  FxEffectDef, TracerDef, WeaponAttachment, WeaponAttachmentUnique, WeaponCamo). Sub-assets are mostly
  aliased in map zones (like FX/material inline cases), so the bulk is the flat struct + string tables +
  a few inline arrays. Build as `native_linker/weaponvariantdef_pc.py` + WEAPON_CAMO consumer.

## ✅ SOLVED (2026-07-07) — it was the `skyBoxModel` XString, not DPVS sizing
`gfxworld_probe2.py::walk()` skipped the **`skyBoxModel` XString @body+36**, which the engine loads
right after `streamInfo` and before `sunLight` (OAT `gfxworld_t6_load_db.cpp:1743`). It is inline
ONLY when the pointer is FOLLOWING; raid's is an alias (`0xa00ed0be` → 0 bytes) so raid alone walked
clean, while nuketown's is FOLLOWING (`0xffffffff`) → inline `skybox_mp_nuketown2020\0` (23 bytes).
That 23-byte under-consumption drifted everything after it (sunLight/volumes/planes/cells → garbage).
**Fix:** consume the XString when `g(36) in PTRS` (one block added after the streamInfo section).
Result: nuketown GfxWorld now fully healthy (cells badBounds=0, trees=1876, models 184/184, surfaces
137/137); raid unchanged. `pc_walk` now walks PAST GfxWorld on all maps: nuketown 624→799, mp_skate
800→802, zm_nuked 1020→1061. Remaining drifts are unrelated later assets (XAnimParts/FX/TechSet).
Everything below is the diagnostic record that led here.

---


## TL;DR — the handoff's diagnosis is WRONG
The drift on non-raid maps is **NOT** in the DPVS sub-array sizing. The DPVS counts
(`smodelCount`, `staticSurfaceCount`, `surfaceCount`) are **already read data-driven** from the
map's own headers in `gfxworld_probe2.py` (`g(dp)`, `g(dp+4)`, `g(16)`). The real drift happens
**far upstream — before `cells`**, i.e. inside the head→cells consumption (volumes / dpvsPlanes
region). By the time the walk reaches DPVS it is already many hundred KB misaligned; the 16/137,
14/81, 5/70 "match rates" in the old handoff are downstream *symptoms*, not the cause.

## Reproduction (all confirmed this session)
- `pc_walk.py` on **raid**: 882/887 clean, walks to end-of-zone. Model is correct for raid.
- **nuketown**: drift @asset 624 GFXWORLD. **zm_nuked**: drift @asset 1020 GFXWORLD. Same wall.
- GfxWorld **head is aligned** on nuketown: body=0x3c39954, fields at +8/+12/+16 (planeCount 15197,
  nodeCount 7528, surfaceCount 5614), sun gate@256=FOLLOW, cellCount@372=25, cells gate@392=FOLLOW,
  dpvsPlanes gates@376/380=FOLLOW — all structurally identical to raid. So bodysize=1028 and the head
  field offsets DO generalize.
- **Everything after the head does NOT.** Applying raid's byte-exact volume+plane+node size model to
  nuketown (identical struct sizes, map-own counts) lands `cells` on garbage: `badBounds=24/25,
  trees=0, portals=0, probeIdx=0` (raid: `badBounds=0, trees=2747, portals=328`). Downstream
  `models boundsOK=0/184`, `surfaces matAliasOK=16/137` — all misaligned.

## What was ruled out
- Wrong GfxWorld body start — NO (head fields align perfectly; 623 prior assets resync clean).
- Head field-offset differences — NO (counts/gates read correct values at raid offsets).
- Untested volume struct sizes — the raid-zero sections (coronas/fogModVol/lutVol) are **also zero**
  on nuketown, so no unexercised size path is being hit.
- Plane struct = 20 bytes — **cannot be validated by "unit-normal" scanning**: even on raid only ~25
  consecutive entries pass a unit-normal test, yet raid's 6958×20 size is provably correct (raid
  walks clean). So plane bytes are NOT all cplanes; do not use normal-magnitude to locate the array.

## The actual open question (for the next session)
Between `sunLight` (first post-head section, 352B) and `cells`, one section's **true byte size does
not equal `count × raid_fixed_stride`** on nuketown — but raid never exposed it because raid's data
happens to make the naive size correct. Prime suspects, in order:
1. **sunLight inline data** — GfxLight may carry an inline def/image on some maps (raid's sun has
   none). If so the first section already under-consumes and everything shifts.
2. **dpvsPlanes region** — `planes`(count g8) and `nodes`(count g12) sizing. Note nuketown inverts
   raid's ratio (more planes, fewer nodes), so a subtle per-element or trailing-array difference here
   would not show on raid.
3. A per-volume inline sub-array (e.g. a *Planes count that is per-volume, not global).

## Recommended method (stop blind scanning — my ad-hoc scanners all failed because the struct
## assumptions were wrong: e.g. raid `model[0]` name-ptr is NULL, not an alias)
Get **ground truth from OAT**: `tools/ref_oat/build/bin/Release_x64/Unlinker.exe` parses these maps
cleanly. Instrument/whitelist the GfxWorld write and dump each sub-array's element count + emitted
byte size, then **diff OAT's per-section sizes against the probe's assumed sizes** on nuketown. The
first section where they disagree is the bug — turning a blind hunt into a one-line diff. This is a
better use of the OAT dependency than the old "STREAM block→flat mapping" idea the handoff feared.

## Files
- `wiiu_ref/gfxworld_probe2.py` — the PC walk (`walk()`), section by section. Head OK; volumes/planes
  → cells is where it silently mis-sizes on non-raid maps.
- `native_linker/pc_walk.py` / `native_linker/gfxworld_pc.py` — consumer; drift surfaces as an
  implausible next-asset name ptr right after GfxWorld.
- Acceptance maps present: `PC ff/mp_nuketown_2020.zone` (@624), `PC ff/zm_nuked.zone` (@1020),
  `mp_skate_pc.zone` (@800 per handoff).
