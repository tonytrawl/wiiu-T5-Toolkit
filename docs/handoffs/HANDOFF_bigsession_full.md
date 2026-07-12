# Handoff: full Wii U / Xbox 360 fastfile pipeline (SOLVE + implement + verify)

Audience: the high-compute session. You own SOLVE, implementation, build, and verification for the work
packages below. This document is self-contained. Do not assume any shared memory with other sessions.
Everything you need (verified state, files, build commands, guards, past mistakes) is here.

Working directory: `C:\Users\Tony - Main Rig\Downloads\Testing enviroment`.
Master reference doc: `WIIU_UNLINK_STATUS.md` (sections 0a..0q). Running log: the `wiiu-native-unlinker`
memory file. Read those, but trust the "Verified state" section below over any older claim in them.

Style rule for all write-ups and code comments: plain, factual, no em dashes.

---

## 0. The three goals

1. Unlink and relink Wii U fastfiles (read a genuine .ff into host assets, write a faithful console .ff).
2. Port DLC that shipped on Xbox 360 to Wii U (360 read -> Wii U write + GPU transcode). Concrete target:
   Nuketown Zombies `zm_nuked.ff`.
3. Port custom maps built on PC to Wii U (PC read, which already works, -> Wii U write + GPU transcode).

The pipeline behind all three: UNLINK (read) -> RELINK (write) -> TRANSCODE (GPU data) -> INTEGRATE
(GSC/IPAK/sound/boot).

---

## 1. Verified state (ground truth, measured on the current tree). Trust this over older notes.

- PC `mp_raid` unlink: `--list` prints "Finished with 0 warnings, 0 errors". This is the regression oracle.
- genuine Wii U `mp_raid` (`wiiu_ref/mp_raid_original.ff`): reads 695 assets, then a clean, intentional
  bail (exit 1, not a crash) on the first skinned XSurface. Order of asset types seen: KEYVALUEPAIRS,
  GLASSES, SKINNEDVERTS, STRINGTABLE, 73 TECHNIQUE_SET, 120 FX, 1 IMPACT_FX, 65+ XMODEL... up to 695.
- genuine Wii U `common_mp` (`common_mp.ff` at repo root): reads 121 assets, then CRASHES inside asset 122
  (type 22 = MENULIST). This is the menuDef console-layout wall (task #27). It is still live. Do not record
  common_mp as "complete"; a prior session claimed 6082/complete and it did NOT reproduce on rebuild. The
  last alias before that crash resolves to a valid aligned pointer, so the fault is genuinely inside the
  menuDef load, not an alias artifact.

Guards you must keep green after every change:
- PC `mp_raid --list` stays "0 warnings, 0 errors".
- genuine `common_mp` still reaches 121 (do not regress below it).
- genuine `mp_raid` still reaches 695 (or further once you extend it).

Console asset layouts already solved and wired into OAT (do not re-derive; they are correct and live):
Material 104, GfxImage 328 (GX2), MaterialTechniqueSet + GX2 vertex(308)/pixel(232) shaders,
MaterialVertexDeclaration 92, SkinnedVertsDef (name*+sv* body), StringTable (PC-identical),
XModel 244, XSurface 128 (static path only), XModelCollSurf 36, clipMap_t 332 (PC-identical),
FX (PC-identical, routing only). Reused-memory alias handling is done (see section 4).

---

## 2. Environment: files, build, run, debug

### Genuine zones and oracles
- Wii U maps: `wiiu_ref/mp_raid_original.ff` (compressed), `wiiu_ref/mp_raid_genuine.zone` (decompressed),
  `zm_transit_original.zone`, `mp_dockside_wiiu.zone`.
- Wii U common: `common_mp.ff` (repo root, genuine v148).
- Wii U skinned corpus: `wiiu_ref/Original FF/faction_*.zone` (240 skinned surfaces: fbi 98, multiteam 116,
  cd 20). Character bodies (faction_*_mp), maps (mp_*).
- PC oracles: `PC ff/mp_raid.ff` + `PC ff/mp_raid.zone` (v147 little-endian), `PC ff/common_mp.ff`.
- 360: `xbox ff/*`, and the DLC target `zm_nuked.ff` (360 v146, LZX). Decompress a .ff to a .zone with
  `python tools/ff_decrypt.py <file.ff>`.

### Probes (executable specs; each is byte-exact where noted)
`wiiu_ref/`: `xmodel_probe.py`, `gfxworld_probe2.py` (pc/wiiu modes, byte-exact end to end),
`clipmap_probe.py`, `fx_probe.py`, `shader_probe.py`, `gfximage_probe.py`, `walker.py`, `wiiu_zone.py`,
`struct_layout.py`. Warning: `struct_layout.py` is known to mis-size structs (it silently drops
pointer-to-array members and mis-sized clipMap_t, GfxLight, GfxLutVolume, GfxWorldFogModifierVolume).
Never trust its sizes; use genuine bytes or the C++ headers as ground truth.

### OAT source and build
- Source: `tools/ref_oat/src`. Build tree: `tools/ref_oat/build`.
- MSBuild: `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe`.
- Common args: `/p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 /p:SolutionDir=<build dir
  with forward slashes and a trailing slash> /m`.
- If you changed codegen (ZoneCodeGeneratorLib / ZoneCodeGenerator / any template), the sequence is:
  1) build `src/ZoneCodeGenerator/ZoneCodeGenerator.vcxproj`,
  2) delete `build/src/ZoneCode/Game/T6.log` (forces regen),
  3) build `src/ZoneCode/ZoneCode.vcxproj` (regenerates the 96 `_load_db.cpp`),
  4) build `src/UnlinkerCli/UnlinkerCli.vcxproj`.
- If you only changed `ZoneLoading` (hand-written readers, ZoneInputStream), just build
  `src/UnlinkerCli/UnlinkerCli.vcxproj`.
- Output: `build/bin/Release_x64/Unlinker.exe`.
- Regen wipes generated files: any debug print you add to a generated `*_load_db.cpp` is lost on regen.
  Put durable debug in hand-written files.

### Running the Unlinker
Stage a copy of the .ff named to its internal name (the Unlinker name-verifies), then:
`OAT_IGNORE_SIG=1 OAT_ALIAS_NULL=1 Unlinker.exe --list <staged>.ff`.
Add `OAT_WIIU_BLOCKREMAP=1` for GUI parity (it does not change the map read result). Internal name is bytes
24..56 of the .ff up to the first NUL (e.g. "mp_raid", "common_mp").

### Debug env flags already present (gated, off by default)
`OAT_DBG_XSURF` (per-surface params + XSurface reader trace + a `[NATIVE]` alias trace),
`OAT_DBG_ALIAS` (alias resolution HIT/MISS/misaligned), `OAT_DBG_MAT`, `OAT_DBG_XM` (generated, lost on
regen). `OAT_ALIAS_FALLBACK`, `OAT_CARRY_XZONE`, `OAT_LENIENT` are alternate alias policies for
experiments.

---

## 3. Implementation patterns (how solved layouts are wired in)

Three mechanisms exist; pick per struct:

A. Generic console divergence (drops + alignment cap). In
`src/ZoneCodeGeneratorLib/Generating/Templates/Internal/BaseTemplate.cpp`:
`CONSOLE_MAX_ALIGN=4` (Wii U PPC caps 64-bit member alignment at 4), `IsConsoleDroppedMember` (void* GPU
handles with `condition never`, PLUS the explicit `IsConsoleRealDrop` table for normal members absent on
console such as XModel::bad and XModelCollSurf collTris/numCollTris), `ConsoleArrayCount` (e.g. techniques
36->32), `ConsoleStructSize`, `ConsoleBaseOffsetForMember`, `MembersInMemoryOrder`. This auto-emits
`(SwapEndianness() ? consoleOffset : pcOffset)` at every fill site. Use for structs that are the same PC
members with shifted offsets or dropped fields.

B. Explicit override for inserted words. When a console struct has NEW fields the PC struct has no member
for (GfxWorldDraw grows by inserted GX2 words; GfxStaticModelDrawInst; GfxLight; GfxWorldFogModifierVolume),
the generic walk cannot express it. Add an explicit size and per-member offset override consulted by
`ConsoleStructSize` / `ConsoleBaseOffsetForMember`. For a struct whose only divergence is trailing growth
with no dereferenced interior pointers (GfxWorldFogModifierVolume has no pointers), a size-only override is
enough. Verify sizes against the numbers in section 5, never against struct_layout.py.

C. Hand-written console reader. When the struct is a wholly different GX2 layout (GfxImage, GX2 shaders,
XSurface), write a reader like the existing ones and hook it in
`src/ZoneCodeGeneratorLib/Generating/Templates/ZoneLoadTemplate.cpp` via a `SwapEndianness()` branch (all
hooks are guarded `m_env.m_game == "T6"`). Existing examples:
- `src/ZoneLoading/Game/T6/XAssets/gfximage/gfximage_actions.cpp` `LoadConsoleImage` (hook in
  `PrintLoadMethod`).
- `src/ZoneLoading/Game/T6/XAssets/materialtechniqueset/materialtechniqueset_console.cpp`
  `LoadConsoleMaterialPass` (hook in `PrintLoadMethod` for MaterialPass).
- `src/ZoneLoading/Game/T6/XAssets/xmodel/xmodel_console.cpp` `LoadConsoleXSurfaceArray` (hook at the top of
  `PrintLoadArrayMethod` for XSurface). New hand-written .cpp must be added to
  `build/src/ZoneLoading/ZoneLoading.vcxproj` after a self-closing `</ClCompile>` (sources are explicit,
  not globbed; do not split the multi-line gfximage entry).

Endianness gotcha: GfxImage embeds a GX2Texture whose words are LITTLE-endian inside the big-endian zone;
GX2 shaders are BIG-endian. Read each struct with the correct endianness per section 0f/0g of the status
doc. All console branches must sit behind `m_stream.SwapEndianness()` so the PC path is byte-for-byte
unchanged.

---

## 4. The reused-memory alias artifact (task #26): the single most important trap

Console (32-bit-consistent) zones point references at block regions the original linker reused for a
different, incompatible type. On the 64-bit host those in-block bytes are stale zone-layout. There are four
variants, all handled in `src/ZoneLoading/Zone/Stream/ZoneInputStream.cpp` under `OAT_ALIAS_NULL`:
1. Out-of-bounds reference -> asset refs to null, data ptrs to a shared zeroed scratch.
2. In-bounds but not in the redirect table, via `ConvertOffsetToAliasLookup` (asset ref) -> null.
3. In-bounds but not in the redirect table, via `ConvertOffsetToPointerLookup` (data ptr) -> scratch; and
   `ConvertOffsetToPointerNative` in-bounds-not-recorded -> scratch.
4. Recorded but type-confused: the recorded slot holds fill-data bytes, so the resolved pointer is
   misaligned. `ConvertOffsetToAliasLookup` HIT(ptr): if the resolved pointer is not 4-aligned, return
   null. This one fixed mp_raid at dub_rock_02 and took it 265 -> 695.

Data pointers get dereferenced, so route them to the zeroed scratch (reads zeros), never null. Asset refs
get skipped by the marker, so route them to null. Note: `ConvertOffsetToPointerNative` must NOT get a
misalignment guard, because its in-block offsets are legitimately odd for byte arrays (partClassification,
pixels, name strings). An attempt to add a misalign guard to `ConvertOffsetToPointerLookup` HIT was neutral
(no change to either zone) and was reverted; do not re-add it without a case that needs it.

`OAT_ALIAS_NULL` is lossy (drops reused references). Fine for read/--list, NOT faithful for relink. The
write path will need those references carried as raw values or a two-pass typed fixup.

---

## 5. Work packages

Each package: SOLVE it (Python, byte-exact probe), implement it in OAT per section 3, build, verify per
section 2, then write the byte-table into the named status-doc section and a one-line memory note. Deliver
a genuine .bin sample and the probe.

### WP-A. Skinned XSurface Latte stream. Goal 1. Start first (it is the current mp_raid stop).
SOLVE: derive the size and layout of the one undecoded Latte stream between `vertsBlend` and `verts0` on a
skinned console XSurface. Corpus: `wiiu_ref/Original FF/faction_*.zone` (240 skinned surfaces) plus
`console_skinned_xsurface_sample.bin`; oracle: `german_shepherd` (nb 56) in `PC ff/mp_raid.zone` (both dog
surfaces). Known anchors: `vertsBlend` size equals the exact PC formula (verified 18342/18342 and
16750/16750), and `verts0` begins at the 24-byte-stride block whose positions equal PC's 4-byte-swapped, so
the gap between them is exactly the unknown stream. Prime lead: correlate the gap with the two undecoded
skinned body scalars at +28 (example 0x001728c0) and +40 (example 0x15), plus vertCount[4] and bone count.
IMPLEMENT: extend `LoadConsoleXSurfaceArray` in `xmodel_console.cpp` to detect skinned (flags&2 or the
pre-verts0 GX2 skin pointers set), consume vertsBlend (PC formula) + the derived Latte stream, then fall
through to the existing static verts0/verts1/vertList/triIndices path (remove the current skinned throw).
VERIFY: mp_raid passes german_shepherd and continues past 695 toward GfxWorld; `xmodel_probe.py` resyncs
all skinned models byte-exact across the 240-sample corpus. Write to section 0l(I). If the encoding
resists, fallback: locate verts0 by the 24-stride byte-content resync and consume the gap opaquely.

### WP-B. GfxWorld, full asset. Goal 1. Runtime-verifiable once WP-A lands.
The tables are already solved (`gfxworld_probe2.py` is byte-exact end to end on mp_raid, zm_transit, and PC).
Four structs diverge; everything else is PC-identical (including GfxSurface 80, GfxStaticModelInst 36, the
lightGrid entries 4 B and coeffs 54 B which are byte-swap-identical to PC). Sizes and key offsets:
- GfxWorld body 1076 (PC 1028). All +48 is inside GfxWorldDraw.
- GfxWorldDraw 116 (PC 68): a leading u32 pad at 0, then reflectionProbeCount@4, reflectionProbes@8,
  reflectionProbeTextures@12, lightmapCount@16, lightmaps@20, lightmapPrimaryTextures@24,
  lightmapSecondaryTextures@28, vertexCount@32, vertexDataSize0@36, vd0(data@44), vertexDataSize1@68,
  vd1(data@76), indexCount@100, indices@104, indexBuffer@108. (PC map, relative to draw: rpc@0, probes@4,
  lightmapCount@12, lightmaps@16, vertexCount@28, size0@32, vd0data@36, size1@44, vd1data@48,
  indexCount@56, indices@60.) GfxWorldVertexData0/1 need a matching small override (data at +4 on console).
- GfxLight 372 (PC 352). Note: 372 is not 16-aligned, so the explicit type_align32(16) is capped on
  console; verify the struct rounds to 4 not 16. GfxLight has one pointer (def, GfxLightDef ref, last
  member). If you cannot pin def's console offset, treat GfxLight as size-only and null def on console
  (lossy, safe for --list), or hand-write a small opaque reader.
- GfxWorldFogModifierVolume 66 (PC 48). No pointers, so a size-only override is enough.
- GfxStaticModelDrawInst 208 (PC 152): cullDist@0, origin vec3@4, packed quat u32[3]@16, scale@28,
  model*@32 (XModel alias), runtime/GX2 words @36..79, lmapVertexInfo[4] x 32 B @80 each
  {lmapVertexColors*@0, 20 B zeroed GX2 regs, numLmapVertexColors u16@24, pad}. Per-record dynamics:
  colors FOLLOW -> numLmapVertexColors x 4 bytes, after the whole array.
Inline sub-assets route through the existing console loaders: reflection/lightmap/outdoor images (328), and
materialMemory entries which are 352 (mp_raid) / 959 (zm) inline console Materials. Implement via mechanism
B (explicit overrides) so the generated GfxWorld loader handles the rest. Write to section 0m/0k(G).

### WP-C. Minor asset-type batch. Goal 1. The tail after GfxWorld. Good compute fodder.
Triangulate and implement, in this effort order:
- Quick (likely PC-identical, ruler+resync): SCRIPTPARSETREE, LEADERBOARD, FOOTSTEP_TABLE(S), RAWFILE, KVP
  (about 23 assets in mp_raid).
- Bounded: GameWorldMp glass blob (about 9.6 KB between two known anchors, 1 asset).
- Medium: DESTRUCTIBLEDEF (piece-tree struct, 8 assets).
- Big: XANIMPARTS (animation is its own format family, 2 assets).
- Big: SOUND / SndBank (2 assets); section 0d already flags a bitfield edge-case here, watch for it.
One byte-exact probe per type against mp_raid (and zm_transit where present). Goal: once WP-A and WP-B land,
mp_raid reads clean to the end. Write to section 0q.

### WP-D. menuDef / MENULIST console layout. Goal 1 completeness only.
The common_mp wall (task #27). Deep menu pointer tree with console divergences. Not map-critical (maps carry
no menus), so this only matters for a full common_mp unlink, not for DLC or custom maps. Do it last unless
you specifically need common_mp complete. Its crash is a genuine layout fault, not an alias artifact
(verified: last alias before it resolves cleanly and aligned).

### WP-E. KEYSTONE: Latte vertex transcode. Goals 3 and 2. Independent, highest strategic value.
Derive the exact bit-level GX2/Latte encoding of the 24-byte console GfxPackedVertex versus the 32-byte PC
one, using the mp_raid PC/Wii U pair (same map, same models, same counts: a perfect Rosetta). For each
shared surface, align PC verts0 to Wii U verts0 and reverse the packing of position, packed normal, tangent,
UV(s), and color. Deliver a round-trip encoder/decoder `wiiu_ref/latte_vertex.py` proven by re-encoding PC
verts into console bytes and matching genuine byte-exact on many surfaces across mp_raid and zm_transit.
This is task #19 and is the thing standing between "unlink" and "make a Wii U map render." Runs in parallel
with WP-A. Write to a new section 0p.

### WP-F. GX2 texture (and shader) transcode. Stage 3, Goals 2 and 3.
Derive GX2 texture de-tiling and swizzle (tiled GX2 to linear, per format BC1/BC3/RGBA8) so images move
between platforms; map shader microcode. Shortcut for custom/DLC content: reference existing Wii U stock
shaders and common assets by name instead of transcoding microcode, so prioritize textures first. Deliver
`wiiu_ref/gx2_texture.py` round-trip verified against genuine image pixels.

### WP-G. 360 unlink foundation. Goal 2. Longest path.
Get genuine 360 read working (task #4, currently blocked at asset 2 GLASSES plus the DELAY/PHYSICAL/STREAMER
blocks OAT asserts on). Handle those blocks (allocate declared-zero runtime blocks as zeroed) and derive any
360-specific struct divergences (v146, LZX, Xenos GPU). Targets: `xbox ff/` zones and `zm_nuked.ff`. The 360
shares the asset enum with Wii U, so most non-GPU structs should match the already-solved console layouts;
the deltas are the GPU assets (Xenos vs GX2) and the block model. Deliver the block policy plus the 360
layout deltas.

### WP-H. Write path (Stage 2). Goal 1 second half; prerequisite for a loadable output in Goals 2 and 3.
Mirror every solved console read layout into the Wii U write template (`ZoneWriteTemplate` and the
corresponding hand-written console writers) so relink emits true console-layout structs, not PC-layout
byte-swapped. Also decide how to carry reused-memory aliases faithfully (raw value or typed fixup), since
`OAT_ALIAS_NULL` drops them on read. Verify by round-trip: read genuine mp_raid, write it back, diff against
the genuine bytes.

---

## 6. Dependency map and suggested order

- Goal 1 (unlink/relink Wii U): WP-A -> WP-B -> WP-C -> WP-H. WP-D optional (common_mp only).
- Goal 3 (PC maps to Wii U): WP-E + WP-F(textures) + WP-H + GSC/integration (tasks #15, #18). Most tractable
  because PC read already works.
- Goal 2 (360 DLC to Wii U): WP-G + WP-E + WP-F. Longest, gated on 360 read.

Parallelizable immediately and independent of each other: WP-A, WP-E, WP-C. If you can only run two, run
WP-A (unblocks the read now) and WP-E (the KEYSTONE every render path needs).

---

## 7. Mistakes made before. Do not repeat them.

- PC asset type 7 is TECHNIQUE_SET, not FOOTSTEP_TABLE. Decode the `[DBG] loading asset ... type=N` numbers
  against the `enum XAssetType` in `src/Common/Game/T6/T6.h`, do not guess.
- Do not trust `struct_layout.py` sizes (it drops pointer-to-array members and mis-sized four structs).
  Use genuine bytes or the C++ headers.
- Do not add any stream-padding or alignment mechanism. The console stream is tightly packed; apparent
  "padding" has always turned out to be an inline pointer payload (SkinnedVertsDef) or a struct-size delta.
- The stream position printed by the Unlinker does not map linearly to the .zone file offset. Correlate
  models by structural signature (surf vertex counts, names), not by raw offset.
- A clean thrown LoadingException (for example the skinned bail) exits 1 with a message; a segfault exits
  with 0xC0000005. Distinguish these before concluding a layout is wrong.
- Verify a fix against all three guards (PC 0-errors, common_mp 121, mp_raid 695) before claiming it.
  A prior "common_mp complete/6082" claim did not survive rebuild; measure, do not assume.
- All console branches behind `SwapEndianness()` and `m_env.m_game == "T6"`. Never regress the PC path.

---

## 8. Verification protocol (so your findings are trustworthy when consumed)

For every layout you deliver:
1. The Python probe must resync byte-exact across at least two genuine zones (mp_raid plus zm_transit or the
   faction corpus), landing exactly on the next asset.
2. After implementing, the three guards stay green and the target zone advances by the expected asset count.
3. Put the exact byte-table (offsets, endianness per field, dropped/added members, array counts, per-item
   stream-consumption formula, alias/FOLLOW handling) in the named status-doc section, plus a genuine .bin
   sample and the probe. That is what makes the finding reproducible without your session's context.
