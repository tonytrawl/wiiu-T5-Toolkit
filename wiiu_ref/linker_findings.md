# WP-H: console write path (linker) findings (2026-07-04)

Session deliverable. Do not merge into WIIU_UNLINK_STATUS.md automatically; this file is the source.
Style: plain, factual, no em dashes.

## Headline

OAT now reads a PC .ff and writes a genuine-CONSOLE-layout Wii U v148 zone, not PC-layout
byte-swapped. Invocation unchanged: `OAT_REWRITE=1 OAT_WRITE_WIIU=1 OAT_WIIU_BLOCKREMAP=1
Unlinker.exe --list <pc>.ff` emits `<name>_rewrite.ff` (raw BE zone; `tools/ff_pack.py` wraps it into
the Wii U container). Full PC mp_raid writes clean (exit 0, 111 MB raw zone, 887 assets + refs = 3096
records). Guards stayed green throughout: PC mp_raid `--list` 0 errors, genuine common_mp 121,
genuine mp_raid 852 (improved from 848, see read-side section).

Measured output quality against genuine Wii U mp_raid:
- 120 XModels from OUR OUTPUT parse with the genuine-format probe (`xmodel_probe.py` structural
  validator + full dynamic walk), 111 matched by name to genuine models.
- 464 shared static surfaces: verts1 (BE f16 uv + raw color) 464/464 BYTE-EXACT vs genuine;
  verts0 21/464 fully byte-exact, all remaining 443 exact in position, binormalSign and pad with only
  normal(snorm16)/tangent(snorm8) quantization residue, exactly the expected non-derivable precision
  loss from section 0p (PC 10-10-10 is lossier than console snorm16).
- The GfxWorld siege-skin tail in the output parses as the genuine 4 GX2 shader subtrees and differs
  from genuine mp_raid in exactly 84 bytes = the 21 rebased alias name-pointer slots (see below).

## 1. Read-side prerequisite work (was WP-C leftovers)

### 1a. Siege-skin tail SOLVED and implemented (read + write)
The ~11.6 KB console-only block between the GfxWorld dynamics end and the next asset is exactly
**4 consecutive MaterialVertexShader-style subtrees** (12-byte body {name FOLLOW, loadDef FOLLOW, 0},
name chars, inline GX2VertexShader 308 + microcode + FOLLOW tables): gpuskin1..4bone.glsl, the
SSkinShaders set. Verified byte-exact on mp_raid (0x40a7ad0..0x40aa61d = 11085 B, lands on the
GameWorldMp body to the byte), zm_transit and mp_dockside (same size 11085 in all three; the blobs are
byte-identical across zones except 21 alias name-pointer slots that reference strings written earlier
in the tail itself, e.g. gpuskin2's attrib names alias gpuskin1's inline "vsin_pos"/"vsin_normal").
- Read: `T6::ConsumeConsoleSiegeSkinShaders` in `materialtechniqueset_console.cpp` (reuses the
  existing ConsumeShaderRef walker), hooked at the end of the generated `Load_GfxWorld` (T6 + swap).
- Write: `T6::WriteConsoleSiegeSkinShaders` in `ZoneWriting/Game/T6/ConsoleWriterT6.cpp` emits the
  genuine blob verbatim from `ConsoleSiegeSkinTail.h` (generated from mp_raid) and rebases the 21
  alias slots by `stream.CurrentZonePointer() + delta` (deltas are BLOCK-offset deltas from genuine,
  NOT byte deltas: the tail has interior linker alignment gains, e.g. +0x5d by the vsin_bone1 string,
  which must be preserved so the console loader's own alignment lands the strings where the aliases
  point). New API: `ZoneOutputStream::CurrentZonePointer()`.
- Result: genuine mp_raid read advanced 848 -> 852 assets (GfxWorld tail consumed; GameWorldMp,
  the glass techset and one more asset now read).

### 1b. The "MAP_ENTS at 47" remap is confirmed WRONG; raw 47 = GLASSES (guard-protected, NOT fixed)
The sole remaining read blocker for genuine mp_raid. After the glass techset (0x40f5989..0x411596c)
the next genuine asset at 0x411596c is a real GLASSES asset: body
`[name FOLLOW][numGlasses=0x2b][FOLLOW][FOLLOW]` + ~9.6 KB of glass records + "glasses(...)" strings,
spanning exactly to the clipMap body at 0x4117f02. The old "9.6 KB GameWorldMp glass blob" is this
asset. OAT's console->PC remap maps raw 47 -> 16 MAP_ENTS, dispatches the MapEnts loader on it,
consumes only 38 bytes, desyncs by 0x251a and segfaults inside clipMap (asset 853) on garbage counts.
The remap fix (raw 47 -> 46 GLASSES, second insert at 48/49 per section 0r flag b) plus a real console
Glasses layout are required to read past 852; both are guard-protected and explicitly out of this
session's scope. Note the crash at 853 is a segfault, not a clean bail; the pre-existing "designed
bail" disappeared because the read now gets further.

### 1c. WP-C minor types: confirmed zero-code
SCRIPTPARSETREE/RAWFILE/KVP/FOOTSTEP_TABLE/GAMEWORLD_MP/DESTRUCTIBLEDEF/XANIMPARTS/SndBank are
PC-identical per scripts_and_minor_findings.md; the generated PC loaders already consume them (KVP,
SPT etc. load today; GameWorldMp verified at runtime this session: reads its full PathData between
GfxWorld and the techset). They cannot be sequentially exercised further until 1b lands. The known
SndBank residual (`?4760:4756` bitfield-walk conditional) is untouched and unreached; note genuine
common_mp SndBank is 4760 and mp_raid 4756, so when SndBank is reached this conditional must be
re-derived, not simply removed.

## 2. Generated console-layout write wiring (ZoneWriteTemplate)

Mirrors ZoneLoadTemplate exactly; all runtime choices behind `m_stream->SwapEndianness()`; PC output
byte-for-byte unchanged (PC mp_raid rewrite still 0 errors):
- `MakeFillOffset` / `MakeFillSize` / `MakeArrayExtent` write-side equivalents consulting the same
  BaseTemplate console helpers and explicit override tables (GfxWorldDraw 116, GfxWorldVertexData0/1
  28, GfxLight 372, GfxWorldFogModifierVolume 66, GfxPackedPlacement 28,
  GfxStaticModelLmapVertexInfo 32). Verified in generated code: MaterialVertexShader `? 12 : 16`,
  techset body `? 136 : 152`, techniques ptr array `? 32 : 36`, XModel `? 244 : 248`, GfxWorldDraw
  `? 116 : 68`, GfxLight `? 372 : 352`, GfxStaticModelDrawInst `? 208 : 152` (fill size, stride and
  varWritten.Inc), lmapVertexInfo stride 32.
- `MakeWrittenMemberAccess` and `MakeReusableInnerOffset` are console-aware: pointer markers and
  reusable back-references are patched at the member's CONSOLE offset in the written body.
- `IsConsoleRealDrop` members (XModel::bad, XModelCollSurf collTris/numCollTris) are neither filled
  nor have their subtrees written on console.
- Matching struct with explicit console size (GfxWorldFogModifierVolume 66 vs 48): console branch
  writes consoleSize-strided records, PC bytes as prefix, inserted words zeroed (mirror of the read
  branch).
- TEMP->VIRTUAL block choice on PtrMethods was already present (task #7); unchanged.

## 3. NEW FINDING: the leaf-struct swap gap, and the write-side fix (FillLeaf)

The generated engine copies "matching cross-platform" (pointer-free) leaf structs RAW on both read
(`Load<T>`) and write (`Write<T>`, `Fill`/`FillArray` of embedded leaf members). Fill only swaps
individually-filled scalars. Consequence: the pre-existing console write emitted little-endian content
for ALL leaf-struct regions (XModelLodInfo, vec3/vec4, cplane_s, cLeaf_s, cbrush_t, XBoneInfo,
GfxLightGridEntry, collision trees, ...). First seen as `lodInfo.dist = 00 00 7a 43` (LE 250.0) in the
output vs genuine `43 7a 00 00`.

Fix (write path only): generated `FillLeaf_<T>` methods for every used pointer-free, non-anonymous,
non-asset leaf struct/union, emitted per writer. They copy member-by-member through the fill accessor
(which swaps scalars), recursing into embedded leaf structs, flattening scalar arrays by base scalar
width, and handling:
- unions: if every alternative decomposes to ONE scalar width (vec3_t -> f32 x3), swap as that scalar
  array; otherwise RAW copy (GfxColor stays byte-order-identical, matching genuine console data).
- bitfields: the storage word swaps wholesale (console bit order inside the word is the separate,
  known section-0d divergence and is not addressed).
All raw `Write<T>` sites (array-pointer, dynamic array, embedded, embedded array, single pointer,
ptr-array loading, WriteArray matching branch) route through `EmitRawWrite`, which emits a
SwapEndianness branch calling FillLeaf per element; embedded leaf members inside FillStruct methods
likewise branch to FillLeaf. Sites whose type has no generated FillLeaf (not in m_used_types, e.g.
T5/T6 rope_client_verts_t, par_t, constraint_t: all runtime-block types) fall back to the raw write.

Supporting runtime fix: `WriteWithFill` in a RUNTIME block used to return a NULL accessor (assert in
debug); the console leaf-swap branch for runtime members (GfxWorld sceneDynModel) crashed on it. It
now hands back a persistent scratch buffer: bytes are discarded (runtime blocks emit no file data) but
the block position still advances.

NOT fixed (documented): the READ side has the same gap in the opposite direction: console reads leave
leaf-struct content big-endian in host memory. --list never cares, but any consumer of console-read
host data (or a genuine round-trip through the host representation) sees BE leaf content. Symmetric
raw copy means a hypothetical full console round-trip is still byte-preserving for those regions.

## 4. Hand-written console writers (mirror of the console readers)

`src/ZoneWriting/Game/T6/ConsoleWriterT6.{h,cpp}` (+ `ConsoleSiegeSkinTail.h`), added to
ZoneWriting.vcxproj. Hooks emitted by ZoneWriteTemplate for T6 only:

- **WriteConsoleXSurfaceArray** (hook: top of WriteArray_XSurface): writes `count` 128-byte console
  GX2 bodies (tileMode/vlc/flags/vc/tc/baseVertIndex, markers at +12/+24/+52/+72/+96, vertInfo counts
  at +16, partBits at +108, GX2 slots zero as genuine) then per-surface dynamics:
  vertsBlend (PC formula, u16 byte-swap), verts0 vc x 24 B and verts1 vc x 8 B via the C++ port of
  `latte_vertex.py::pc_vertex_to_console` (BE f32 xyz; BE snorm16 normal from
  normalize(ThirdBased-decode), truncate-toward-zero x32768; BE snorm16 binormalSign 0x7fff/0x8000;
  snorm8 tangent x128; zero pad; BE f16 uv = the two halves of the PC packed u32; color = raw 4-byte
  copy), vertList 12-byte entries + XSurfaceCollisionTree 40 + nodes 16 (u16 fields) + leafs u16,
  triIndices tc x 3 x BE u16 tightly packed.
  Limitations: the three console-only Latte skin streams (+28/+40 counts, markers +32/+36/+44) are
  not derivable from PC data and are emitted absent (markers 0). Reused-geometry surfaces whose verts
  alias another model on the host are re-inlined as FOLLOW (valid format, larger zone) because the
  hand writer bypasses the Reusable machinery below the surfs array itself.
- **WriteConsoleImage** (hook: top of Write_GfxImage): builds the 328-byte body: inline GX2Texture
  with LITTLE-endian words (dim/wh/depth/mips/format/use/imageSize/mipSize/mipmaps/tileMode/
  alignment/pitch/mipLevelOffset[13]) computed by a C++ port of `gx2_texture.py::surface_info` /
  `mip_chain` (micro tm2 / macro tm4 selection by the macro-tile-fit rule, BCn block dims, pitch and
  height alignment, PIPE_INTERLEAVE base align); BE PC tail (mapType..hash) at +156..+327; name chars
  immediately after the body (reorder rule); inline pixels only when streaming==0 (with the caveat
  that PC pixels are linear, not tiled; the supported path is IPAK streaming). T6->GX2 format map:
  6->0x31, 9->0x32, 0xA->0x33, 0x14->0x35, 3->0x07, else 0x1a. Swizzle written 0 (stored swizzle ids
  are inert per section 0q). streamedParts: part 0 from the host bitfields (packing of the
  levelCount:4/levelSize:28 word is a best guess, unverified against genuine).
- **WriteConsoleMaterialPass** (hook: top of Write_MaterialPass): the pass body is already emitted by
  the technique's array fill with null sub-slots; D3D11 bytecode cannot become GX2 microcode, so the
  vertexShader/vertexDecl/pixelShader/args slots stay null (the console reader accepts null markers;
  OAT self-load is unaffected). Real ports must reference stock techsets by name. One-line stderr
  notice on first use.
- **WriteConsoleSiegeSkinShaders** (hook: end of Write_GfxWorld): section 1a above.
- **WriteConsoleGlassesStub** (hook: WritePtr_Glasses, TEMP): emits the genuine 16-byte stub
  `FFFFFFFF 00024000 FFFFFFFF FFFFFFFF` and marks the asset pointer FOLLOW.
- **SkinnedVertsDef** (template-emitted, no new function): after the members, marks the
  maxSkinnedVerts slot FOLLOW and writes the 4 genuine payload bytes (0x00000000).

## 5. Validation status

1. Round-trip identity (genuine -> write -> diff): NOT RUNNABLE yet. OAT_REWRITE only writes after a
   full successful load, and genuine mp_raid still dies at asset 853 (GLASSES remap, section 1b) and
   genuine common_mp at 121 (menuDef). This oracle unblocks when the remap lands.
2. PC mp_raid -> console write: clean (exit 0, 0 errors, 887 assets). Content validated against
   genuine Wii U mp_raid as the Rosetta (headline numbers above): XModel bodies/geometry format
   correct per the genuine-format probes, verts1 byte-exact, verts0 exact except the expected
   sub-10-bit normal/tangent quantization, siege tail byte-exact modulo the 21 rebased alias slots.
3. Self-load (pack with ff_pack.py, OAT --list the output): reads 182 assets (SPT, techsets,
   materials, images, xmodels) then segfaults at asset 183, the first FX. OPEN: bounded residual,
   likely one divergence in an FX-referenced inline subtree (next step: OAT_DBG_WR on the write and
   the [DBG] read trace on the crash asset, diff consumption per member).
4. Guards after every change and at the end: PC mp_raid --list 0 warnings 0 errors; genuine common_mp
   121; genuine mp_raid 852 (up from 848). PC rewrite (non-WiiU) also still 0 errors.

## 6. Open items, ranked

1. Self-load crash at the first FX (validation 3): bisect and fix; this gates "OAT --list the output
   cleanly".
2. Console->PC asset-type remap + console GLASSES layout (guard-protected, section 1b): gates both
   the full genuine read and the round-trip oracle.
3. Reader-side console->PC vertex decode (console_vertex_to_pc port): would make the host
   representation uniform so a genuine console read can be re-emitted through the same writer, and
   would fix the BE-content leaf gap for geometry on read.
4. GfxImage streamedParts word packing + image hash: verify against genuine streamed images; IPAK
   hash parity belongs to the other session's ipak work.
5. MaterialPass: reference-techset emission strategy (write `,techset` reference assets instead of
   inline passes) for hardware-loadable output.
6. Alias fidelity: OAT_ALIAS_NULL reads drop reused-memory references, and OAT_NO_REUSE at write
   time is UNUSABLE for GfxWorld (the cells<->portals cycle relies on reuse back-references;
   disabling it recurses until crash; found and documented this session). Faithful alias carry
   remains the task-#26 write-side design question.

## 7. Files touched

- src/ZoneCodeGeneratorLib/Generating/Templates/ZoneLoadTemplate.cpp (GfxWorld tail hook + include)
- src/ZoneCodeGeneratorLib/Generating/Templates/ZoneWriteTemplate.cpp (console wiring, FillLeaf
  machinery, hand-written writer hooks, Glasses/SkinnedVertsDef mirrors)
- src/ZoneLoading/Game/T6/XAssets/materialtechniqueset/materialtechniqueset_console.{h,cpp}
  (ConsumeConsoleSiegeSkinShaders)
- src/ZoneWriting/Game/T6/ConsoleWriterT6.{h,cpp}, ConsoleSiegeSkinTail.h (NEW; in ZoneWriting.vcxproj)
- src/ZoneWriting/Zone/Stream/ZoneOutputStream.{h,cpp} (CurrentZonePointer, runtime-scratch
  WriteWithFill)
- src/ZoneWriting/Game/T6/ContentWriterT6.cpp (gated OAT_DBG_WR per-asset write trace)
- Full regen of the generated tree (T6.log deleted; all debug instrumentation used during bring-up
  was in generated files and is gone after the final regen).

## 8. Repro commands

- Build: ZoneCodeGenerator.vcxproj, delete build/src/ZoneCode/Game/T6.log, ZoneCode.vcxproj,
  UnlinkerCli.vcxproj (all `-p:Configuration=Release -p:Platform=x64 -p:PlatformToolset=v143
  -p:SolutionDir=<build>/`).
- Write: `OAT_REWRITE=1 OAT_WRITE_WIIU=1 OAT_WIIU_BLOCKREMAP=1 Unlinker.exe --list mp_raid.ff`
  (PC staged copy). Do NOT add OAT_NO_REUSE (GfxWorld cycle, section 6.6).
- Pack: `python -c "import ff_pack; open('out.ff','wb').write(ff_pack.pack_ff(open('mp_raid_rewrite.ff','rb').read(),'mp_raid'))"` (tools/).
- Geometry check: the collect/compare harness in this session's transcript wraps xmodel_probe's
  parse_surface_dyn to extract (vc, verts0, verts1) per model from any zone-like blob and diffs
  against wiiu_ref/mp_raid_genuine.zone.
