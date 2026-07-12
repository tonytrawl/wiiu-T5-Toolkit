# HANDOFF — Genuine GfxWorld inline + asset-ref remap (the last wall for Raid render)

## State: infrastructure BUILT, remap TOOL remaining (needs the byte-exact GfxWorld walker)

GfxWorld is the confirmed last crash wall (drop it → clean). Our PC->WiiU GfxWorld matches genuine in
every structural aspect checkable, yet crashes (heap overrun in DB_GumpShouldFree). Fix = inline the
GENUINE WiiU GfxWorld (which has all correct console content: GX2 regs, streaming data, correct dpvs)
with its internal asset-references REMAPPED to our zone's same-named assets.

## Already built (this session)
1. `OAT_GFXWORLD_FILE=<blob>` hook in `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/gfxworld/
   gfxworld_t6_write_db.cpp` (function Write_GfxWorld). Console-only. Writes the blob verbatim:
   memcpy blob[0:1068] over the GfxWorld body (offset 8..1076, i.e. past name@0/baseName@4 which we keep
   via WriteXString), then Write blob[1068:] as dynamics, + IncBlockPos headroom. UNLINKER ALREADY REBUILT.
2. Raw genuine blob: `wiiu_ref/gfxworld_raid.blob` = genuine[gfxworld_body+8 .. asset end] = 22,258,552
   bytes (1068 body-tail + all dynamics). NOTE: raw — its internal aliases still point to GENUINE offsets;
   it will crash on dangling refs until remapped.
   Genuine GfxWorld: body @0x2b7029d, end (=GameWorldMp) @0x40aa61d, in `wiiu_ref/mp_raid_genuine.zone`.

## Remaining: the remap tool  `wiiu_ref/gfxworld_remap.py`
Produce `gfxworld_raid_remapped.blob` from the raw blob by rewriting every internal ASSET-REFERENCE alias
(block-5 VIRTUAL pointer to another asset) so it points at OUR zone's same-named asset.

### Which fields are asset-refs (from the write path + T6_Assets.h)
- `materialMemory[materialMemoryCount=352]` : each `MaterialMemory{Material* material; int memory}` (8B) →
  material@+0 is a Material asset alias. THE BIG ONE.
- `draw.reflectionProbes[].reflectionImage` : GfxImage alias (+ probeVolumes internal).
- `draw.lightmaps[].primary/.secondary` : GfxImage aliases.
- `draw.reflectionProbeTextures / lightmapPrimaryTextures / lightmapSecondaryTextures` : GfxTexture* —
  runtime handles, likely 0xFFFFFFFF/null on console (verify; probably no remap).
- `cells[].reflectionProbes` : char* index list (self-contained, NOT asset ref).
- `outdoorImage` (GfxImage), `skyBoxModel` (XModel), `sunflare_t.spriteMaterial/.flareMaterial` (Material).
- `models[]` = GfxBrushModel = SELF-CONTAINED (bounds + surface indices, no asset ref — skip).
- dpvs `surfaceMaterials` = GfxDrawSurf = material INDEX packed, self-contained (skip).

### Remap algorithm
1. Build genuine asset map: VIRTUAL-offset → (assetType, name). Build our-zone map: name → VIRTUAL-offset.
   - Get these by dumping each zone's asset list + walking to each asset body. Two options:
     (a) extend the OAT reader with an env like OAT_DUMP_ASSET_OFFSETS to print (type,name,virtualOffset)
     per asset while it reads (genuine reads fully; our zone segfaults at asset 3 — so for OUR map, use
     the native `wiiu_ref/wiiu_zone.py` + `walker.py`, or dump during WRITE via a ContentWriterT6 hook
     that logs each asset's written VIRTUAL offset + name — the WRITE side knows both);
     (b) simplest for OUR side: add a diagnostic to ContentWriterT6 that logs (assetName, virtualOffset)
     for every Material/GfxImage/XModel as it's written → gives name→our-offset directly.
2. Locate each asset-ref field's byte position INSIDE the blob. THIS REQUIRES the byte-exact GfxWorld
   walker (see HANDOFF_dpvs_walker.md — extend it to walk the WHOLE GfxWorld, tracking field offsets, not
   just the dpvs). The walker gives, e.g., "materialMemory array @ blob offset X"; then material aliases
   are at X + i*8 for i in 0..351.
3. For each alias A at blob position P: decode block-5 offset → look up genuine map → name → our map →
   our offset → re-encode alias → write into blob at P. (Decode: blk=(v-1)>>29, off=(v-1)&0x1FFFFFFF;
   encode: v = (blk<<29 | off) + 1.)
4. If a referenced asset name is NOT in our zone (shouldn't happen for a same-name port), fall back to a
   ",name" reference (byte pattern the loader DB_Find-resolves) or null.
5. Write `gfxworld_raid_remapped.blob`. Self-check: re-walk it, confirm every asset-ref alias now decodes
   to a valid OUR-zone asset offset.

## Build + test (once remapped blob exists)
```
OAT_REWRITE=1 OAT_IGNORE_SIG=1 OAT_WRITE_WIIU=1 OAT_DROP_GSC=1 \
  OAT_GFXWORLD_FILE=wiiu_ref/gfxworld_raid_remapped.blob \
  OAT_GAMEWORLDMP_FILE=wiiu_ref/gameworldmp_raid.blob \
  OAT_MAPENTS_FILE=wiiu_ref/mapents_raid.blob \
  OAT_TECHSET_DIR=wiiu_ref/techsets_raid \
  OAT_IMAGE_DIR=<scratch>/img_out OAT_OMIT_LIST=<scratch>/omit_snd_scr_img.txt \
  tools/ref_oat/build/bin/Release_x64/Unlinker.exe --list "PC ff/mp_raid.ff"
python WiiU_FF_Studio/wiiu_ff.py pack mp_raid_rewrite.ff mp_raid mp_raid_GFXINLINE.ff && cp ... mp_raid.ff
```
User loads on Wii U. DONE WHEN: geometry renders (no crash) — first rendered map, and captures the exact
genuine GX2/dpvs content format to later SYNTHESIZE for DLC maps (which have no genuine WiiU version).

## Caveat / interaction with the dpvs-walker diagnostic (HANDOFF_dpvs_walker.md)
If that diagnostic finds a STRUCTURAL dpvs desync in our WRITER, fixing it may make our PC-derived GfxWorld
load without the inline (cheaper, DLC-general). Run that diagnostic first/in parallel; the inline is the
guaranteed fallback if our GfxWorld is structurally clean (→ crash is content, only inline fixes it).
Context: memory `track-a-ipak-streaming`, entries 2026-07-05 night11-15.
