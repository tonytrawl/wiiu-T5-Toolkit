# WP-B: GfxWorld console layout IMPLEMENTED (2026-07-04)

Status: DONE and verified. Genuine Wii U mp_raid now reads the full GfxWorld asset (848)
byte-exactly and advances to asset 849 (GameWorldMp, unported, WP-C). All three guards green:
PC mp_raid `--list` = 0 warnings 0 errors; genuine common_mp = 121 (unchanged); genuine mp_raid
= 848 complete + clean bail inside 849 (exit 1, VIRTUAL overflow inside GameWorldMp, NOT a
segfault; the old segfault-at-848 is gone).

Style note: this file is the WP-B write-up for the merge pass. Do not merge into
WIIU_UNLINK_STATUS.md automatically; sections 0m/0k(G) are the target.

## 1. New codegen mechanism (mechanism B): explicit console override tables

`src/ZoneCodeGeneratorLib/Generating/Templates/Internal/BaseTemplate.{h,cpp}`:

- `ConsoleExplicitStructSize(info)` and `ConsoleExplicitMemberOffset(member)` (both return
  SIZE_MAX when no override, both gated `m_env.m_game == "T6"`). Consulted by:
  - `StructHasConsoleDivergence` (explicit size present -> diverges),
  - `ConsoleStructSize` (explicit size wins over the accumulate walk),
  - `ConsoleBaseOffsetForMember` (explicit offset wins; members without an entry fall back to
    the accumulate walk -- lossy but safe for scalars).
  This is what lets a console struct INSERT words the PC struct has no member for.

`src/ZoneCodeGeneratorLib/Generating/Templates/ZoneLoadTemplate.cpp`:

- Embedded-array and dynamic-array FillStruct loops now use `MakeFillSize(type)` as the element
  stride instead of the PC `GetSize()` (needed for GfxStaticModelDrawInst::lmapVertexInfo[4],
  console stride 32 vs PC 12).
- `LoadMember_ArrayPointer`: a matching-cross-platform (pointer-free) struct with an explicit
  console size gets a console branch that `LoadWithFill(consoleSize * count)`s and copies each
  record's PC-sized prefix through a stack temp (fill region shares block memory with the
  destination array; forward copy through a temp is overlap-safe because consoleSize > pcSize).
  Used by GfxWorldFogModifierVolume (66 vs 48).

## 2. The override tables (ground truth, genuine mp_raid + zm_transit)

| struct | console | PC | notes |
|---|---|---|---|
| GfxWorldDraw | 116 | 68 | leading u32 pad @0; member offsets below |
| GfxWorldVertexData0/1 | 28 | 8 | `data` @ +4; rest is GX2 vertex-buffer regs |
| GfxLight | 372 | 352 | 20 inserted bytes at the FRONT, then the PC 352 layout VERBATIM (+20) |
| GfxWorldFogModifierVolume | 66 | 48 | no pointers; size-only override |
| GfxPackedPlacement | 28 | 52 | origin @0, packed quat u32[3] @12, scale @24 |
| GfxStaticModelLmapVertexInfo | 32 | 12 | lmapVertexColors* @0, 20 B GX2 regs, numLmapVertexColors u16 @24 |

GfxWorldDraw console member offsets: pad@0, reflectionProbeCount@4, reflectionProbes@8,
reflectionProbeTextures@12, lightmapCount@16, lightmaps@20, lightmapPrimaryTextures@24,
lightmapSecondaryTextures@28, vertexCount@32, vertexDataSize0@36, vd0@40 (data@44),
vertexDataSize1@68, vd1@72 (data@76), indexCount@100, indices@104, indexBuffer@108.

GfxStaticModelDrawInst 208 and GfxWorld body 1076 need NO explicit entries: they emerge from
the generic accumulate walk once GfxPackedPlacement=28, lmapVertexInfo elem=32 and
GfxWorldDraw=116 are in the table (verified: generated offsets match gfxworld_probe2.py CFG
exactly: lightGrid@512, models@584/588, materialMemory@620/624, sun@628, outdoorImage@788,
shadowGeom@824, lightRegion@828, dpvs@832, dpvsDyn@948, occluders@1036/1040, size 1076).

### GfxLight, fully pinned (upgrades the handoff's "size-only, null def" fallback)

Console GfxLight = 5 console-only u32 at +0 (mp_raid values 0xeb0 0xeb3 0x1189 0x118a 0x1190,
look like shadow/index words), then the ENTIRE PC 352-byte layout shifted +20, INCLUDING the
PC align-16 interior padding (diffuseColor@108, viewMatrix@228, projMatrix@292, def@356).
def is a real GfxLightDef asset ref at +356 and is null in both mp_raid and zm_transit sun
lights, so it is kept (not dropped). Implemented as a blanket `PC offset + 20` rule.
Evidence: PC/console word-alignment of the mp_raid sun light (color 14/13.37/11.586 and unit
dir at PC+8/PC+20 reappear at console +28/+40; diffuseColor row repeats at +108).
Note the probe's "sunLight" section boundaries were already correct; 20+352=372 exactly.

### GfxWorldDraw texture slots are runtime words

Genuine console draw words +12/+24/+28 (reflectionProbeTextures, lightmapPrimary/Secondary
Textures) hold 0xFFFFFFFF (runtime fill), NOT real refs. Loading them as FOLLOW desyncs.
Added to `IsConsoleRealDrop` so the console fill zeroes them (their offsets stay in the
explicit table because they occupy real words in the 116-byte body). PC path unchanged.

## 3. Two hand-written runtime fixes (survive regen)

- `src/ZoneLoading/Zone/Stream/ZoneInputStream.h` `ZoneStreamFillReadAccessor::Fill<T>`:
  replaced the typed assignment with `std::memcpy`. The typed load let MSVC emit ALIGNED SSE
  moves; console fill offsets can be misaligned for over-aligned types (float44 viewMatrix at
  console offset 228 inside the 372-byte GfxLight fill => segfault). This was the actual crash
  at asset 848.
- `src/ZoneLoading/Loading/Steps/StepAllocXBlocks.cpp`: on console (swapEndianness), NORMAL
  blocks get TEMP-declared-size headroom. The console path redirects TEMP data into VIRTUAL,
  which the zone's declared VIRTUAL size does not account for.

## 4. Verification detail

- Byte-exactness: instrumented the generated loader with per-section VIRTUAL-block offsets and
  diffed every section delta against gfxworld_probe2.py marks across the whole ~10 MB asset.
  All content sections match EXACTLY (e.g. lightmaps 0x180165, indices 0xb0e98, entries
  191048, coeffs 0x2b0cda, smodelInsts 168048, smodelDrawInsts+lmapColors 0x385d30 =
  4668x208 + 680732x4, occluders 340, lutMaterial inline chain 0x40288). Remaining deltas are
  host-side Alloc alignment padding only (e.g. +8 for Alloc<GfxStreamingAabbTree>(16), +124
  for the 128-aligned sortedSurfIndex), which consumes no stream bytes.
- Loader lands exactly on the probe's GFXWORLD END (0x40a7ad0) = start of asset 849.
- vd0/vd1 world vertex streams: consumed byte-exact via the size fields (36 B/vert world
  format, both platforms). The section 0p Latte primitives cross-check applies to the vertex
  CONTENT (BE f32 positions etc.) and is consistent with the byte-swap-identical observation;
  full content decode of the 36 B world vertex is a write-path task, not needed for read.

## 5. Leads handed to WP-C (do not lose these)

- Asset 849 = GameWorldMp (console raw type 16). Its console body at 0x40a7ad0 is
  `FFFFFFFF FFFFFFFF 00000000` (12 bytes, two FOLLOWs + zero) followed immediately by an
  inline chunk starting with the string "gpuskin1bone.glsl" then binary (0x01090000 ...).
  So console GameWorldMp embeds a console-only GPU-skin GLSL blob (this is the "glass blob"
  gap; PC GameWorldMp is {name, PathData path} = 44 B). The current loader mis-parses it as
  the PC 44-byte body and overflows VIRTUAL. This is the sole blocker before MapEnts/clipMap.
- Console->PC asset-type REMAP is partly wrong. Histogram alignment of genuine console
  mp_raid raw types vs the PC oracle shows: single +1 shift for raw 8..47 (insert at 7 only),
  +2 for raw >= 50 (second insert at raw 48 or 49, NOT at 44), and raw 47 aligns with PC 46
  GLASSES (count 1<->1, adjacent position), so the "MAP_ENTS relocated to 47" rule appears to
  be a myth that survived via the 16-byte Glasses stub hack. Console extras vs PC: one extra
  SOUND (raw 10 x2 vs PC 9 x1) and one raw 48 asset. NOT changed in this session (out of
  WP-B scope, guard risk); revisit together with the GameWorldMp fix.
- zm_transit sunLight is preceded by GfxWorld::skyBoxModel inline ("skybox_zm_transit"),
  which gfxworld_probe2.py does not model (it lumps the string into its fixed sections and
  self-corrects later). The OAT loader handles it correctly as an XString member.

## 6. Files touched

- src/ZoneCodeGeneratorLib/Generating/Templates/Internal/BaseTemplate.h / .cpp (override tables,
  GfxTexture drops)
- src/ZoneCodeGeneratorLib/Generating/Templates/ZoneLoadTemplate.cpp (strides + matching-struct
  console-size array branch)
- src/ZoneLoading/Zone/Stream/ZoneInputStream.h (Fill memcpy)
- src/ZoneLoading/Loading/Steps/StepAllocXBlocks.cpp (TEMP headroom for NORMAL blocks)
- Generated tree rebuilt clean (T6.log deleted, all *_load_db.cpp regenerated; debug traces
  used during bring-up were injected into generated files only and are gone after the final
  regen).
