# HANDOFF — Task #28 IMPLEMENT: map-zone console layouts (SkinnedVerts, StringTable, XModel/XSurface, clipMap, GfxWorld body)

**From:** SOLVE sessions 2026-07-03/04 (pure-Python triangulation, no OAT changes made).
**To:** the implementing session (owns `tools/ref_oat` C++ builds).
**Authoritative reference:** `WIIU_UNLINK_STATUS.md` §0k + §0l (byte tables), reference parsers in
`wiiu_ref/` (each is a byte-exact executable spec), genuine samples saved per struct.

**Everything below is VERIFIED byte-exact against genuine zones** (mp_raid_genuine.zone,
zm_transit_original.zone, + faction zones), except where explicitly marked OPEN.

---

## 0. Test matrix (know what "done" looks like)

| Zone | Today | After implementing this handoff |
|---|---|---|
| `common_mp` (genuine Wii U) | 121 assets | unchanged (no map assets early) — regression guard |
| `mp_raid_genuine` | 4 assets, crashes at StringTable | reads through StringTable, techsets, then FX (see §6 caveat), XMODELs, GfxWorld body… stops at GfxWorld *dynamics* (OPEN) |
| PC zones | must not regress | must not regress (all changes behind `SwapEndianness()`) |

Implementation order below = dependency/payoff order. Items 1–2 are trivial; 3 is the big one;
4 is medium; 5 is body-only.

---

## 1. SkinnedVertsDef — the mp_raid crash blocker (trivial fix)

**The "4-byte stream padding" does not exist.** Console `SkinnedVertsDef` = 8-byte body
`{+0 name*, +4 sv*}` — PC's scalar `maxSkinnedVerts` is a **pointer** on console. When word +4 is
FOLLOW (it is, in all 3 genuine zones), consume **4 inline bytes** (observed 0x00000000) after the
name chars, then null the field (runtime data).

- Verified at 3 different end-offset phases (mod 8 = 6, 2, 4) → provably not alignment.
- OAT hook: same pattern as the Glasses stub fix (a `ZoneLoadTemplate` console branch for T6
  SkinnedVertsDef): load name, read u32 marker, if FOLLOW/INSERT consume 4 bytes, null, done.
- **Do NOT add any generic stream-padding/alignment mechanism.** The stream is tightly packed;
  the doctrine stands.

## 2. StringTable — no work, just confirm

PC-identical: body 20 `{name*, columnCount, rowCount, values*, cellIndex*}`,
`StringTableCell` = 8 `{string*, hash}`. The native walker consumed mp_raid's 142,048-byte
StringTable and resynced byte-exact. Once item 1 lands, this should just work. If columnCount
still reads -1, the SkinnedVerts fix is wrong — do not touch StringTable itself.

## 3. XModel / XSurface / XModelCollSurf — the big one

Reference parser: **`wiiu_ref/xmodel_probe.py`** (port its walk exactly).
Sample: `wiiu_ref/console_xmodel_sample.bin` (p_glo_tools_rake incl. inline material+images).
Verified: **mp_raid 260 models / 223 byte-exact chain resyncs / 0 failures; zm_transit 64 / 0.**

### 3a. Console XModel = 244 bytes (PC-32 248)
PC's `bool bad` @212 (+3 pad) is **dropped**; tail shifts −4. Offsets +0..+211 PC-identical.
Console tail: `+212 physPreset*, +216 numCollmaps u8(+3), +220 collmaps*, +224 physConstraints*,
+228 lightingOriginOffset vec3, +240 lightingOriginRange` → 244.
- Codegen route: this is a *dropped non-pointer member* — extend the console-drop mechanism
  (like `IsConsoleDroppedMember`) with a per-struct table entry for `XModel::bad`, or hand-write.
  The tail shift must flow into the fill offsets.
- Dynamic order = member order (no reorder): name chars, boneNames 2×nb, parentList nb−nrb,
  quats 8×(nb−nrb), trans 16×(nb−nrb), partClassification nb, baseMat 32×nb, surfs,
  materialHandles 4×ns, collSurfs, boneInfo 44×nb, himipInvSqRadii 4×ns, physPreset, collmaps,
  physConstraints.

### 3b. Console XSurface = 128 bytes (PC 80) — a GX2 struct, hand-write it
NOT a shifted PC struct (like GfxImage). Full table in §0l/§0k(D). Key fields:
`+0 tileMode u8, +1 vertListCount u8, +2 flags u16 (1=quantized,2=skinned,0x80=deformed),
+4 vertCount u16, +6 triCount u16, +8 baseVertIndex u16, +12 triIndices*,
+16 vertInfo.vertCount[4] i16 (PC-identical), +24 vertsBlend* (skinned), +28 u32 skinned scalar,
+32/+36/+44 skinned-only ptrs, +40 u32, +52 verts0*, +72 verts1* (NEW console-only stream),
+96 vertList*, +108 partBits[5]` → 128.

**Static per-surface dynamic order (byte-exact):**
1. `verts0` = vertCount × **24 B** (xyz BE float32 + 12 B packed Latte attrs)
2. `verts1` = vertCount × **8 B** (console-only second vertex stream)
3. `vertList` = vertListCount × XRigidVertList(12); per entry, collisionTree FOLLOW →
   XSurfaceCollisionTree(40) + nodes(16×n) + leafs(2×n)
4. `triIndices` = triCount × 3 × BE u16, **tightly packed** (PC's tdef_align(16) does NOT pad
   the stream)
All consumption marker-driven (FOLLOW/INSERT), exactly as in `parse_surface_dyn`.

**SKINNED surfaces (flags & 2, or +24 == FOLLOW): the pre-verts0 weight blob is UNSOLVED**
(variable-length Latte-packed skinning data; 240 samples characterized it but no closed formula —
§0l(I)). **Implement as: detect skinned → fail/skip that model gracefully** (e.g. null the asset
and resync is impossible mid-stream, so: abort the zone read cleanly OR, better, don't attempt —
map zones contain ~2 skinned viewmodels each and they are the LAST models you'd hit). Do not guess.

### 3c. Console XModelCollSurf_s = 36 bytes (PC 44)
PC's `collTris*` + `numCollTris` are **dropped**: `{+0 mins vec3, +12 maxs vec3, +24 boneIdx,
+28 contents, +32 surfFlags}`. **No dynamic data** (no collTris follow!).

### 3d. Inline sub-assets inside XModel
- `materialHandles` entries FOLLOW/INSERT → **full inline console Material asset** — reuse the
  already-implemented console Material(104)/GfxImage(328)/techset/GX2-shader loaders. This is why
  Material/GfxImage/shader had to land first; it's already in your tree.
- `physPreset` FOLLOW → inline PhysPreset(84, PC-identical) + name + sndAliasPrefix strings.
- `collmaps` FOLLOW → Collmap(4) → PhysGeomList(12) → PhysGeomInfo(68) → BrushWrapper(96) +
  sides(12×n, per-side plane FOLLOW→20) + verts(12×n) + planes(20×n). All PC-32-identical.

## 4. clipMap_t — solved, PC-identical (medium effort, mostly "just works")

Reference parser: **`wiiu_ref/clipmap_probe.py`**. Sample: `console_clipmap_sample.bin`.
Verified byte-exact end-to-end: mp_raid body @0x4117f02 → lands on techset 853 TO THE BYTE;
zm_transit @0x62c3a02 → lands on the next Material to the byte.

**Console clipMap_t = PC-identical, 332 bytes, ALL element sizes PC-identical.** In principle OAT's
existing PC path + generic byte-swap should handle it with NO console conditionals. Two real
action items:

1. **⚠ Verify OAT's own T6 clipMap_t struct has `uint16_t (*triIndices)[3]` at +120 and
   sizeof == 332.** Our Python `struct_layout.py` silently dropped this pointer-to-array member
   (reported 328, tail offsets −4). OAT's C++ headers presumably have it right (it's real C++),
   but the ZoneCodeGenerator's handling of pointer-to-array members on the console/fill path is
   exactly the kind of place a mirror bug could live. One genuine-byte check: mp_raid body
   0x4117f02+120 must be FOLLOW (it is) and consume triCount×6.
2. Full field map + element sizes in §0l(J) — use it to spot-check the generated loader:
   ClipMaterial 12 (+inline name strings), cbrushside_t 12 (plane reusable→aliases),
   cLeafBrushNode_s 20 (+`data.leaf.brushes` u16×leafBrushCount when >0), cbrush_t 96,
   cStaticModel_s 84, cNode_t 8, cLeaf_s 44, verts 12, tris 6,
   triEdgeIsWalkable = ((3·triCount+31)/32)·4, CollisionPartition 16, CollisionAabbTree 32,
   cmodel_t 76, visibility numClusters×clusterBytes, **inline MapEnts (36, PC-identical incl.
   embedded MapTriggers)**, box_brush 96, DynEntityDef 84, PhysConstraint 168,
   pose/client/server/coll lists RUNTIME (0 bytes), ropes RUNTIME.
3. Note: `ClipInfo.planes` and several arrays are `reusable` → in map zones they're ALIASES to
   GfxWorld's already-written data (OAT's alias machinery handles this; `OAT_ALIAS_NULL` semantics
   from task #26 apply if any miss).

## 5. GfxWorld — implement the BODY ONLY (dynamics are OPEN)

**Console GfxWorld body = 1076 bytes (PC-32 = 1028).** Now cross-validated against PC mp_raid
(identical counts at the mapped offsets on both platforms). Table in §0k(G):
- +0..+395 PC-identical.
- **GfxWorldDraw @396 = 116 bytes on console (PC 68)** — the entire +48: GX2 buffer words added
  around vd0/vd1/indices (exact word map in §0k(G)).
- GfxLightGrid @512 PC-identical (72); tail = PC tail shifted (modelCount@584 … lightingQuality@1072).

**⚠ DO NOT implement the dynamic-stream walk from the old §0k(G) bullet list** — it was corrected
in §0l: content verification only holds through dpvsPlanes.planes/nodes; the cells→reflectionProbes
region desyncs and everything after is unanchored. Known-correct pieces you MAY rely on: section
ORDER (= member order), and vd0/vd1/indices byte sizes (from body fields, identical on PC).
- **New console divergence identified (unsolved): the lightGrid data is FAT on console** — ~5 MB of
  36-byte light-sample records (xyz + ±1.0 + masks) vs PC's 4-byte entries + 54-byte coeffs.
- Practical effect: a sequential mp_raid read will parse the GfxWorld body then fail in its
  dynamics. Acceptable for this increment; SOLVE continues in parallel with the PC oracle
  (PC GfxWorld body @0x3f34930 in `PC ff/mp_raid.zone` — all anchors in §0l).

## 6. Known walls you'll hit BEFORE the above pays off (expectations)

- **FX (FxEffectDef): console layout NEVER derived.** mp_raid has 164 FX assets starting around
  asset ~10 — likely the first wall after StringTable/techsets, BEFORE the XMODEL region. If FX
  blocks the read, report back — that's a bounded SOLVE task (same triangulation method).
- DESTRUCTIBLEDEF (8), FOOTSTEP_TABLE (7), SOUND (2), XANIMPARTS (2), SCRIPTPARSETREE (13),
  LEADERBOARD — also in mp_raid's asset list, also underived. SCRIPTPARSETREE/RAWFILE/KVP are
  simple and probably fine; the others are unknowns.
- So: **don't judge the XModel/clipMap implementations by "mp_raid reads 889 assets"** — judge by
  targeted verification (below).

## 7. Verification protocol (per struct, independent of the walls)

The SOLVE probes print exact genuine offsets — use them as oracles against OAT debug output:
1. **SkinnedVerts/StringTable:** mp_raid must read ≥5 assets, StringTable columnCount==1,
   rowCount==0x2406, and the read continues into techsets.
2. **XModel:** instrument the loader to print each XModel's start/end VIRTUAL+stream pos; compare
   with `python wiiu_ref/xmodel_probe.py` output (260 models with exact extents). Even if the
   sequential read can't reach the XMODEL region because of FX, you can verify the layout compiles
   + PC regression, and rely on the probe's 223 chained byte-exact resyncs as ground truth.
3. **clipMap:** mp_raid clipMap spans 0x4117f02..0x454d50e in the decompressed zone — if OAT
   reaches it (after GfxWorld dynamics are solved), its consumption must match. Until then:
   PC regression (PC mp_raid.ff --list must not change) is the main guard, since clipMap's
   console path == PC path.
4. **Always:** genuine `common_mp` still reads 121 assets; PC common_mp/mp_raid list 0 errors.

## 8. Files & artifacts inventory

| Artifact | What it is |
|---|---|
| `WIIU_UNLINK_STATUS.md` §0k, §0l | byte tables + corrections (§0l supersedes §0k(H) and the §0k(G) dynamics claims) |
| `wiiu_ref/xmodel_probe.py` | executable spec: XModel/XSurface/collSurf + inline material/physpreset/collmap consumption |
| `wiiu_ref/clipmap_probe.py` | executable spec: full clipMap walk incl. inline MapEnts + dynEnt tail |
| `wiiu_ref/gfxworld_probe.py` | body decoding good; dynamic walk NOT trustworthy past dpvsPlanes |
| `wiiu_ref/console_xmodel_sample.bin` | genuine XModel incl. inline material+images |
| `wiiu_ref/console_clipmap_sample.bin` | genuine clipMap body + first 8 KB |
| `wiiu_ref/console_skinned_xsurface_sample.bin` | genuine skinned surface (for the future weight-stream RE) |
| `wiiu_ref/console_gfxworld_sample.bin` | genuine GfxWorld body + 4 KB |
| `wiiu_ref/Original FF/faction_*.zone` | 240 skinned-surface corpus (future) |
| `PC ff/mp_raid.zone` | PC oracle (same map as mp_raid_genuine) — keep, SOLVE needs it |

## 9. Hard don'ts

- No stream-padding/alignment mechanism (item 1 is a pointer field, not padding).
- Don't implement skinned-surface weight-blob consumption by guesswork — detect & bail.
- Don't implement GfxWorld dynamics past the body from the old notes.
- Don't "fix" struct_layout.py's triIndices bug by changing OAT structs — verify OAT's own
  clipMap_t is already 332 first.
- All console branches behind `m_stream.SwapEndianness()` (+ T6 game guard in templates, as with
  GfxImage) — PC paths must be byte-for-byte unchanged.

---
---

# ADDENDUM (2026-07-04, second SOLVE pass) — SUPERSEDES §5 and §6 above

Everything below was solved after the original handoff was written. Read WIIU_UNLINK_STATUS.md
**§0m** (new) alongside §0k/§0l.

## A1. FX (FxEffectDef) — the predicted "FX wall" does not exist as a layout problem

Console FX = **PC-IDENTICAL everywhere**: FxEffectDef 76, FxElemDef 292, velSamples 96,
visSamples 48, FxTrailDef 28 (+verts 20×n, inds 2×n), FxSpotLightDef 12, all FxEffectDefRef
slots = assetref name strings, spawnSound string. The generated PC-layout loader should work
on console **except for one routing rule**: when an `FxElemVisuals` value is FOLLOW/INSERT,
the inline asset must be loaded with the CONSOLE loaders you already have:
- elemType ≤ 6 (sprites/tail/line/trail/cloud) and DECAL markArray entries → console **Material**
- elemType == 7 (MODEL) → console **XModel**
- SOUND → soundName string; RUNNER → effect name string (plain, no console branch needed)
OAT presumably already dispatches these through Load_MaterialPtr / Load_XModelPtr — if so, FX
needs NO new code at all once Material/XModel console loaders are in. Verify with
`wiiu_ref/fx_probe.py` outputs (mp_raid 46/46, zm_transit 116/116, mp_carrier 21/21 zero-fail)
and `console_fx_sample.bin`.

## A2. GfxWorld — now implement the FULL asset (body + dynamics), §5 above is obsolete

`wiiu_ref/gfxworld_probe2.py` is the executable spec — a parallel PC/WiiU walker verified
byte-exact end-to-end on mp_raid (ends exactly on the next asset @0x40a7ad0) and zm_transit
(@0x613d809), with the PC zone as cross-oracle (identical counts everywhere, e.g. 680,732
lightmap vertex colors on both platforms).

**Only FOUR structs diverge on console** (full tables in §0m):
1. `GfxWorld` body **1076** (PC-32 1028) — all +48 inside `GfxWorldDraw` = **116** (PC 68);
   GX2 buffer words around vd0/vd1/indices. lightGrid @+512, tail shifted +48. (§0k G table.)
2. `GfxLight` = **372** (PC 352). ⚠ OAT's generated size may be wrong the same way our Python
   tool was (it reported 480) — VERIFY the generated console/PC sizes against these numbers.
3. `GfxWorldFogModifierVolume` = **66** (PC 48). Single genuine sample (zm_transit),
   content-locked between two verified anchors.
4. `GfxStaticModelDrawInst` = **208** (PC 152):
   `+0 cullDist f32, +4 origin vec3, +16 packed quat u32[3], +28 scale f32, +32 model* (XModel
   alias), +36..79 runtime/GX2 words, +80 lmapVertexInfo[4] × 32 B {lmapVertexColors* @+0,
   20 B zeroed GX2 regs, numLmapVertexColors u16 @+24, pad2}` → 208.
   Per-record dynamics: colors FOLLOW → count×4 bytes (after the whole array, standard order).

**Everything else in GfxWorld is PC-identical** — including `GfxSurface` = 80 (material @+48),
`GfxStaticModelInst` = 36, lightGrid entries 4 B / coeffs 54 B (data byte-swap-identical to PC),
`GfxBrushModel` 64, `MaterialMemory` 8, `Occluder` 68, `GfxHeroLight` 56, heroLightTree records
32 (`{mins,maxs,left,right}`), cells/aabbTrees/portals/probes, all volume arrays
(lutVolume = 36). Inline sub-assets inside GfxWorld that MUST route to console loaders:
- reflection probe images, the lightmap secondary image, outdoorImage → console GfxImage(328)
- **materialMemory entries: 352 (mp_raid) / 959 (zm) inline console Materials** — this is where
  the map's world materials live; sunflare sprite/flare materials may also inline (zm does)
- lutMaterial (INSERT) → inline console Material incl. its techset + LUT image.

## A3. Corrections to facts stated earlier in this file / §0k

- §5's "do NOT implement GfxWorld dynamics" is LIFTED — §0m is the verified spec.
- §6's "FX console layout never derived / likely first wall" — resolved, see A1.
- The old §0k(G) claim that a 36-byte "console GfxSurface" and a fat 36-byte lightgrid exist is
  RETRACTED (misreads at a desynced cursor; root cause was GfxLight=480 vs real 372).
- ⚠ **Do not trust ZoneCodeGenerator/struct_layout-computed sizes blindly** for: clipMap_t
  (must be 332 with triIndices@+120), GfxLight (352/372), GfxLutVolume (36),
  GfxWorldFogModifierVolume (48/66). Our Python layout tool got all four wrong; check whether
  OAT's generator has equivalent bugs (pointer-to-array members and similar edge cases).

## A4. Updated expectations for mp_raid

With everything in this file implemented, genuine mp_raid should read: KVP, Glasses stub,
SkinnedVerts, StringTable, techsets, **FX, XMODELs (static), GFXWORLD (fully), MAP_ENTS,
CLIPMAP_PVS**, rawfiles, SCRIPTPARSETREE (likely PC-identical)… The remaining read-stoppers are
the still-underived minor types: **DESTRUCTIBLEDEF (8), XANIMPARTS (2), SOUND/SndBank (2),
FOOTSTEP_TABLE(s) (7+1), LEADERBOARD (1), GAMEWORLD_MP glass blob (1)** — and skinned XSurfaces
(detect-and-bail per §3b). Report which one blocks first; each is a bounded SOLVE task.

## A5. New artifacts since the original handoff

| Artifact | What |
|---|---|
| `wiiu_ref/fx_probe.py` | executable FX spec (zero-fail on 4 zones) |
| `wiiu_ref/console_fx_sample.bin` | genuine FX region sample |
| `wiiu_ref/gfxworld_probe2.py` | executable GfxWorld spec, `pc`/`wiiu` modes, per-section validators |
| `wiiu_ref/clipmap_probe.py` + sample | (from first pass) clipMap spec |
| `PC ff/mp_raid.zone` | decompressed PC oracle — keep |
