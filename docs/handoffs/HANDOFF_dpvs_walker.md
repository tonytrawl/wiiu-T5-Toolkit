# HANDOFF — Finish the byte-exact GfxWorld dpvs walker (offline diagnostic)

Self-contained. A cold session can run this. NO hardware needed. Goal: build a walker that fully
parses a genuine Wii U `GfxWorldDpvsStatic` and lands EXACTLY on the next asset (GameWorldMp), then
run the same model on our PC->WiiU converted GfxWorld to find the first structural desync (or prove
there is none).

## Project one-liner
Reverse-engineering Black Ops II (T6) Wii U fastfiles to port PC maps/DLC to Wii U. The load pipeline
is hardware-confirmed for everything EXCEPT GfxWorld, which crashes the Wii U (heap overrun in
`DB_GumpShouldFree`). Every GfxWorld section EXCEPT the dpvs byte-matches genuine; the dpvs is the one
unverified part. This task verifies it.

## Paths / tools
- Python: `C:/Users/Tony - Main Rig/AppData/Local/Programs/Python/Python313/python.exe`
- Genuine Wii U zone (decompressed, big-endian): `wiiu_ref/mp_raid_genuine.zone`
- Our converted zone (decompressed): `mp_raid_rewrite.ff` (regenerate if stale — recipe below)
- Existing partial walker: `wiiu_ref/gfxworld_probe.py` (walks all GfxWorld sections but STOPS at the
  dpvs head — it only prints `dpvs head words` and returns). Extend from there.
- Struct source: `tools/ref_oat/src/Common/Game/T6/T6_Assets.h` (struct `GfxWorldDpvsStatic` etc.)
- Write path (authoritative array order + console sizes): `tools/ref_oat/build/src/ZoneCode/Game/T6/
  XAssets/gfxworld/gfxworld_t6_write_db.cpp`, function `Write_GfxWorldDpvsStatic` (also `_load_db.cpp`).
- Prior incomplete attempt: `<scratchpad>/dpvs_walk.py` (fit DrawInst size; undershoots — incomplete
  visData model + missing GfxWorldDpvsDynamic + trailing GfxWorld sections).

## Known ground truth (verified this session)
- Our GfxWorld body @ `0x3fcdd15` in `mp_raid_rewrite.ff`; genuine GfxWorld body @ `0x2b7029d`,
  genuine GfxWorld ENDS at GameWorldMp body `0x40aa61d` (target end for genuine walk).
  Find our body by searching for the map-invariant dpvs count triple `6958,19402,5281`
  (`struct.pack('>III',6958,19402,5281)`) — it's at gfxworld_body+8.
- dpvs body is embedded at gfxworld_body+832 (console). dpvs body = 116 bytes.
  Field offsets (console, from struct_layout): smodelCount@0, staticSurfaceCount@4, litSurfsBegin@8,
  litSurfsEnd@12, litTransSurfsBegin@16, litTransSurfsEnd@20, emissiveOpaqueSurfsBegin@24, ...End@28,
  emissiveTransSurfsBegin@32, ...End@36, smodelVisDataCount@40, surfaceVisDataCount@44,
  smodelVisData@48 (ptr[0]), 52 [1], 56 [2], surfaceVisData@60 [0], 64 [1], 68 [2],
  smodelVisDataCameraSaved@72, surfaceVisDataCameraSaved@76, sortedSurfIndex@80, smodelInsts@84,
  surfaces@88, smodelDrawInsts@92, surfaceMaterials@96, surfaceCastsSunShadow@100,
  surfaceCastsShadow@104, smodelCastsShadow@108, usageCount@112.
- Genuine mp_raid dpvs counts: smodelCount=4668, staticSurfaceCount=5194, smodelVisDataCount=4736,
  surfaceVisDataCount=5248. OUR zone has the SAME counts (verified).
- dpvs static array SERIALIZATION ORDER (from Write_GfxWorldDpvsStatic; each guarded by its ptr being
  FOLLOW/INSERT; markers = 0xFFFFFFFF or 0xFFFFFFFE):
  1. smodelVisData[0],[1],[2]  (align 128 each)
  2. surfaceVisData[0],[1],[2]
  3. smodelVisDataCameraSaved
  4. surfaceVisDataCameraSaved
  5. surfaceCastsSunShadow
  6. surfaceCastsShadow
  7. smodelCastsShadow
  8. sortedSurfIndex (uint16, align 2, count=staticSurfaceCount)
  9. smodelInsts (align 4, count=smodelCount)
  10. surfaces (align 4, count=staticSurfaceCount)
  11. smodelDrawInsts (align 4, count=smodelCount)
  12. surfaceMaterials (align 4, count=staticSurfaceCount)
  visData arrays are `raw_byte128` = `tdef_align32(128) char` = sizeof 1, count = the *VisDataCount.
  (An earlier fit suggested esz might be 128 — RESOLVE THIS: the byte size of each visData array is the
  #1 open question. Genuine smodelVisData[0] extent divided by smodelVisDataCount = the true esz.)
- Console struct sizes (OAT overrides, applied to BOTH write+load): GfxSurface=80, GfxStaticModelInst=36,
  GfxStaticModelDrawInst= (OAT uses an override; struct_layout says 136 — VERIFY against genuine),
  GfxDrawSurf=8, GfxPackedPlacement=28 (console packed quat, NOT PC 52).
- AFTER the dpvs static comes GfxWorldDpvsDynamic (@body+948 console) then more GfxWorld trailing
  sections (occluders, outdoorBounds, heroLights, heroLightTree, sceneDynModel, sceneDynBrush, etc.)
  — see the tail of `Write_GfxWorld` for the exact order. The full walk must include these to reach
  0x40aa61d.

## Task
1. Extend `gfxworld_probe.py` (or a new script) to FULLY parse GfxWorldDpvsStatic + GfxWorldDpvsDynamic
   + the trailing GfxWorld sections, following the write path's exact order/alignment/sizes.
2. FIT the uncertain sizes (visData element size; GfxStaticModelDrawInst size) so the GENUINE walk from
   gfxworld_body+dpvs-array-start lands EXACTLY on 0x40aa61d (GameWorldMp). The genuine dpvs arrays
   start where gfxworld_probe's genuine walk ends before the dpvs head (~0x3536c79). This VALIDATES the
   model against real hardware layout.
3. Run the SAME validated walker on OUR GfxWorld (`mp_raid_rewrite.ff`, body 0x3fcdd15). Check whether
   it lands exactly on OUR GameWorldMp (find our GameWorldMp via `struct.pack('>II',750,750)` minus 4).
   - If it DESYNCS (doesn't reach our GameWorldMp): report the exact sub-array where our cursor
     diverges from genuine's expected size. That is the writer bug — a wrong console size/count in that
     dpvs sub-struct. Fix in `gfxworld_t6_write_db.cpp` + `_load_db.cpp` (keep write==load) + the
     ConsoleExplicitStructSize override in `BaseTemplate.cpp` if it's a struct size, then regen.
   - If it walks CLEAN to our GameWorldMp: report that — it proves our GfxWorld is 100% structurally
     sound, so the crash is NOT a stream desync (it's content/GPU/reference), and the main session
     should commit to the genuine-GfxWorld INLINE path.

## Regenerate mp_raid_rewrite.ff if needed (from project root)
```
OLD=<scratchpad-798d568c>/scratchpad   # img_out + omit_snd_scr_img.txt live here
OAT_REWRITE=1 OAT_IGNORE_SIG=1 OAT_WRITE_WIIU=1 OAT_DROP_GSC=1 \
  OAT_GAMEWORLDMP_FILE=wiiu_ref/gameworldmp_raid.blob \
  OAT_MAPENTS_FILE=wiiu_ref/mapents_raid.blob \
  OAT_TECHSET_DIR=wiiu_ref/techsets_raid \
  OAT_IMAGE_DIR=$OLD/img_out OAT_OMIT_LIST=$OLD/omit_snd_scr_img.txt \
  tools/ref_oat/build/bin/Release_x64/Unlinker.exe --list "PC ff/mp_raid.ff"
```
(Do NOT rebuild the Unlinker; it's already built. This just regenerates mp_raid_rewrite.ff.)

## Deliverable
The exact answer to: "does our GfxWorld dpvs structurally desync, and if so, in which sub-array and by
how many bytes?" Report the fix (writer size/count change) or the clean result (→ inline path).
Full context: memory `track-a-ipak-streaming` entries dated 2026-07-05 night11-15.
