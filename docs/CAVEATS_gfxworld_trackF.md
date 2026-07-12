# CAVEATS — Track F GfxWorld region generators (2026-07-10)

Deliverable: `native_linker/gfxworld_emit.py :: emit_gfxworld(pc_zone, gw_off, ctx)
→ (bytes, fixups, log)`. All raid GfxWorld regions emit; validated byte-exact vs the
mp_raid oracle mod the classes below, with mp_dockside second-map spot-checks.
mp_skate emits end-to-end (22.89 MB artifact: `skate_gfxworld_trackF.bin` +
`_fixups.json`). Supporting modules (all Track F–owned): `gfxworld_regions.py`
(cells, materialMemory), `gfxworld_gx2.py` (probes/lightmaps/outdoor/tail-material
images), `gfxworld_smodel.py` (smodelDrawInsts — SOLVED, no stub), 
`gfxworld_streaminfo.py` (streamInfo synthesis).

## ⚠ INTEGRATION REQUIREMENTS (assemble session)
1. **Inline techsets are EXCLUDED from emitted material streams** (materialMemory,
   sunflare, tail material). When a material's techniqueSet ptr is FOLLOW/INSERT the
   console loader expects an inline console techset there. The assemble must either
   (a) inject the Track B substitute techset blob at those positions, or (b) rewrite
   the ptr word to the substitute's alias. Positions are findable via
   `gfxworld_regions._console_material_pieces` on the emitted stream. **Without this
   the zone stream is NOT loadable.**
2. `fixups` = offsets (into the returned bytes) of pointer words carrying PC block-5
   alias values → rewrite through the loader-sim omap. FOLLOW/INSERT/null verbatim.
3. Material `hashIndex` (console body @32) is per-zone, console-computed — emitted
   as the PC value; recompute at assemble if the console hash table differs.
4. `ctx['image_source']` (PC-ipak resolver) is REQUIRED for the tail lut material's
   resident image; without it the lut image falls back to a streamed stub.
5. Emitted streamed-image headers use swizzle 0 and part hashes tiled with swizzle 0
   — the authored ipak must be built from the same entries (MC.COLLECT_ENTRIES) so
   header and payload stay paired. (Genuine console used swizzle 0x30000; ours is
   self-consistent, not byte-identical.)

## Registered SYNTHESIS (not byte-comparable, structurally validated)
- **streamInfo.aabbTrees/leafRefs**: KD median-split over smodel bounds (≤16/leaf),
  DFS ordering; satisfies all genuine invariants (partition, subtree ranges,
  contiguous child blocks). Deltas vs genuine: each smodel appears ONCE (genuine
  duplicates boundary-spanning models → possible slightly-late texture stream-in);
  streamDist2 = constant 6.0e7 (genuine varies per node). Layout quirk pinned: the
  region begins with 16 bytes 0xFF, and the count field understates the array
  (probe spans sit -16/-20 off the real arrays).

## Registered REENCODE (content-equal, encoder differs)
- **draw.lightmaps**: PC RGBA8 → console BC3 via our range-fit encoder after the
  512-row-block restack (k → row k//2, col k%2; W×H → 2W×H/2). Decode-back diff vs
  genuine ≈ BC3 noise (2.8 raid / validated rule on dockside). Genuine encoder is
  slightly different (unknown) — cosmetic.
- **tail lut image**: console lut asset is platform-authored (`*_ps3` vs `*_win`);
  we emit the PC (`_win`) content restacked (16×64×64 tiles → vertical). Genuine
  differs by ±small requantization + name/hash. Preserves the PC look.

## Console-rebuild divergences (PC-consistent output, engine-valid)
- **cells aabbTrees**: console rebuilds per-cell trees with a different split
  heuristic (23/47 raid cells differ by a few nodes). We emit the PC-built tree —
  self-consistent (same class as reorder_pc). Equal-count cells verify byte-exact
  mod ≤3-ULP bound floats + smodelIndexes alias ptr.
- **material stateBits tables**: console dedups (e.g. 5→3 entries). We emit the PC
  table + PC stateBitsEntry — self-consistent pair.
- **dpvs.sortedSurfIndex**: console re-sorts by a comparator that resolves through
  per-platform material bodies; we keep PC order (draw-order optimization only).
- **samplerState remap**: 0x?4 class −9 (aniso→trilinear, 1289-texdef oracle rule);
  the exception (keep 0x14 / use 0x13) is a per-image property (mips) — resolvable
  via ctx['sampler_lookup'] once image meta lookup exists; fallback −9 on ~10% of
  texdefs is a cosmetic filtering nuance.
- **reflection probe LOD bias @72**: 0.0 (−5.0 for micro-tiled tiny probes),
  matching genuine; PC stores −8.0.

## Allowlist classes (byte-diff but expected)
- Pointer/alias words (the fixups list). GX2 header words 9/11 (baked runtime
  image/mip pointers — we emit 0). 1-ULP float rounding (platform map-compile).

## Known-absent shapes (loud failures, not silent)
- `fogModVol` (console 66B vs PC 48B stride) — raises NotImplementedError; not
  present on raid/dockside/skate. Multi-lightmap maps and lightmap shapes not
  divisible into 512-row pairs also raise.

## Oracle validation summary (mp_raid / mp_dockside)
| Region | Result |
|---|---|
| body 1076B | exact mod fixups + one 1-ULP float |
| cells | portals 328+286/…, pverts, probeidx, eq-count cells 24+14: exact |
| materialMemory | entries 352+390, bodies 348+379, names/consts: exact |
| reflectionProbes | exact mod 1-ULP floats + hdr words 9/11 (both maps) |
| outdoorImage | exact mod hdr word 9 (both maps) |
| lightmaps | header exact mod word 11; pixels = BC3-noise |
| smodelDrawInsts | 4668+3030 insts + color tails: EXACT mod alias words |
| smodelCastsShadow / occluders / sunLight | exact (verbatim / swap4 / w0+swap4) |
