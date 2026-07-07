# WP-A findings: skinned console XSurface Latte stream (SOLVED, implemented, verified)

Date: 2026-07-04. Owner: WP-A session. This file is the WP-A write-up for later merge into
WIIU_UNLINK_STATUS.md section 0l(I) and the memory note (do not merge here; single-pass merge later).

## The formula

A skinned console XSurface (flags & 2, or any of the pre-verts0 GX2 skin markers at +24/+32/+36/+44
set) serializes this inline region between the 128-byte body array and verts0:

```
vertsBlend bytes = (vertCount[0] + 3*vertCount[1] + 5*vertCount[2] + 7*vertCount[3]) * 2   (exact PC formula)
latte gap  bytes = 2*lo16(s28) + 2*hi16(s28) + 2*s40
```

where `s28` is the u32 body scalar at +28 and `s40` the u32 at +40 (both big-endian). The gap is
three console-only u16 streams whose FOLLOW markers sit at +32, +36 and +44, consumed in ascending
marker order with element counts lo16(s28), hi16(s28), s40 respectively. The total is what stream
resync needs; the per-marker count assignment follows marker order and the observed content
boundaries (stream 1 is bone/vertex run records with bone offsets in multiples of 0x40, streams 2
and 3 are short per-run u16 tables). tensionData has no console pointer slot; +28/+40 hold the
counts instead ("+28 always alias" in the old 0l(I) note was a misread: it is a packed count pair,
not a pointer).

Example (viewmodel_hands_cloth surf0, sample bin): vc=2123, vertCount=(744,980,298,101),
s28=0x001120c0 (hi=17, lo=8384), s40=17 -> vertsBlend 11762 + gap 2*8384+2*17+2*17=16836 = 28598
pre-verts0 bytes, byte-exact to the file.

Example (german_shepherd surf0, genuine mp_raid): vc=2883, vertCount=(1093,742,742,306),
s28=0x001728c0 (hi=23, lo=10432), s40=21 -> vertsBlend 18342 + gap 20952. Surf2: vertsBlend 16750,
s28=0x000e2780 (hi=14, lo=10112), s40=21 -> gap 20294.

After the region, the surface continues on the already-solved static path: verts0 (vc x 24),
verts1 (vc x 8), vertList (+trees), triIndices (tc x 6). Aliased markers carry no inline data,
same as the static streams.

## Evidence (all byte-exact)

- Probe: `wiiu_ref/skinned_probe.py`. Corpus: the 4 faction zones + genuine mp_raid.
  Result: 35 skinned models, 668 skinned surfaces, 0 failures. Per surface: every verts0 position
  (all vc verts) inside the model's mins/maxs, every triIndex < vertCount; per model: the cursor
  lands exactly on the materialHandles marker array (fbi 164, multiteam 195, cd 158, isa 149,
  mp_raid 2). Note: scan must use step 1, not 4 - mp_raid's dog body sits at a %4==3 file offset.
- `console_skinned_xsurface_sample.bin` surf0 consumes to the exact byte (file truncates 107 bytes
  into surf1's verts0).
- PC oracle: german_shepherd (nb=56, ns=3) in `PC ff/mp_raid.zone` vs `mp_raid_genuine.zone`:
  surf0 vertsBlend 9171/9171 u16s byte-swap-identical, verts0 positions 8649/8649 floats identical,
  triIndices 13164/13164 identical (PC unaligned at that site); surf1 positions 3531/3531 identical.
  (surf2 compare desynced on the PC-side walk of surf1's vertList trees - a probe-side PC walk
  detail, irrelevant: the Wii U side resyncs byte-exact onto materialHandles and the inline
  mc/mtl_german_shepherd material.)
- Rejected candidate for the record: gap = 2*lo16(s28) + 4*s40 fits only surfaces where
  hi16(s28) == s40 and fails the corpus.

## Implementation

`src/ZoneLoading/Game/T6/XAssets/xmodel/xmodel_console.cpp`:
- `ConsumeSurfaceDynamics` now consumes, before verts0: vertsBlend (PC formula) when +24 is FOLLOW,
  then the three Latte streams (2*lo16(s28), 2*hi16(s28), 2*s40 bytes) when +32/+36/+44 are FOLLOW.
  Host has no members for the console streams; consumed and dropped. vertsBlend/tensionData stay
  null on the host (--list never walks them).
- `ConsoleSkinnedSurfaceException` and the skinned throw removed; skinned surfaces fall through to
  the static verts0/verts1/vertList/triIndices path.
- Build: UnlinkerCli only (ZoneLoading-only change), builds clean.

## Verification (the three guards, current tree)

1. PC `mp_raid --list`: "Finished with 0 warnings, 0 errors".
2. Genuine `common_mp`: still 121 assets, then the known type=22 MENULIST crash (task #27 wall,
   unchanged).
3. Genuine Wii U `mp_raid`: 695 -> 848 assets. Passes german_shepherd and all subsequent
   XModel/Material/techset tiers; new stop is asset 848, type=17 = GFXWORLD (segfault inside the
   unported GfxWorld console layout). That is exactly WP-B's starting point.

Run flags: `OAT_IGNORE_SIG=1 OAT_ALIAS_NULL=1`.
