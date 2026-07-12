# HANDOFF — Track F/G: no-backbone console-zone assembly (mp_skate build frontier)

Date 2026-07-07. mp_skate PC walk is END-TO-END, so it's a valid no-backbone build candidate. This is
the frontier that turns a walked PC map into a bootable Wii U .ff. Orientation + the key de-risking
finding below; task breakdown is in the session task list (#1 asset-list author, #2 GfxWorld region
generators, #3 assemble+pack).

## What exists (build on these)
- `native_linker/produce_pc_ff.py` — VALIDATION harness only: uses the *genuine console* raid zone as
  backbone, proves PC-converted bodies == genuine. NOT a no-backbone assembler (needs a console zone
  to exist). It's the oracle pattern, not the builder.
- `native_linker/pc_to_console.py` — `PCConverter`: converts SIMPLE identical-layout types
  (StringTable/KeyValuePairs/RawFile/ScriptParseTree/Localize/FootstepTable/Leaderboard) PC->console
  (BE byte-swap + alias omap). Validated == genuine.
- Complex converters (per memory, validated byte-exact): Material (Track A), Techset (Track B),
  XModel (Track C), FX header (Track D). GfxWorld geometry: `gfxworld_assemble.py` + `gfxworld_dynamics`.
- `wiiu_ref/ipak_stream.py` — image/.ipak authoring is GENERAL and no-backbone-ready (byte-exact vs
  retail mp_la 287/287). The image half is DONE.
- `native_linker/zone_stream.py` — `ZoneWriter` with the console block model (BLOCK_TEMP=0, PHYSICAL=2,
  VIRTUAL=5, +runtime variants 1/3/7), `encode_ptr(block,off)` = `((block<<29)|(off&0x1FFFFFFF))+1`.
- Console zone format (`wiiu_ref/wiiu_zone.py`): header [u32 size, u32 externalSize, u32 blockSize[8]]
  (40B), then string table (count, ptrs, strings), then asset array (count, ptr, N×{u32 type, u32
  headerPtr}), then bodies in block-stream order. v148 BE.

## KEY FINDING (de-risks the frontier): the console asset list is DERIVABLE from PC
The old "unknowable console reorder" fear is unfounded. Measured PC raid list vs genuine console raid
list: **99.77% identical order.** Console = PC order with exactly:
1. **Type remap PC->console** (invert `wiiu_zone.console_to_pc`): `t>44 -> +2`, `t>6 -> +1`, and the
   GLASSES(46)/MAP_ENTS(47) pair (the PC[850] GLASSES == console[851] MAP_ENTS is a 46<->47 relabel,
   the same asset — NOT a real diff).
2. **2 console-only inserts** (889 vs 887): a **GLASSES at console index 1** (right after
   KEYVALUEPAIRS[0]), and an **extra SOUND** right after the existing SoundBank entry (~index 872).
### MULTI-MAP VALIDATION (2026-07-07) — the raid-only rule did NOT generalize (guard paid off)
Validated the derivation on raid + dockside + zm_transit (all have console oracles). Result: the
**bulk order is derivable** (PC order + type remap, sim ≥0.9975 on all three), but the **console-only
inserts are MAP/MODE-SPECIFIC** — NOT the universal "GLASSES@1 + SOUND" the raid-only measure implied.
Per-map console-only asset multiset (genuine CO minus PC):
- **MP — raid: {MAP_ENTS +1 (inline), SOUND +1 (inline)}. dockside: SAME.** (2/2 MP maps agree.)
- **ZM — zm_transit: {GLASSES +3 (aliased refs at front), LEADERBOARD +1 (inline), LOCALIZE_ENTRY +9
  (inline), XGLOBALS −1 (dropped)}.**
Corrections to the earlier raid reading: the "GLASSES@1" is the map's own GLASSES *moved to the front*
(aliased ref); the genuine console-only asset on MP is **MAP_ENTS** (inline) + a duplicate **SOUND**.
The type remap (invert `console_to_pc`) is validated; `pc_type 16` is ambiguous (console 17 and 47=MAP_ENTS
both map to it) — disambiguate by the source asset, not the number.

**Consequence for the mp_skate build:** mp_skate is MP, and the MP insert pattern (MAP_ENTS + extra
SOUND) holds on BOTH available MP maps — usable with reasonable confidence. The ZM insert pattern is
different and belongs to the zombies phase (alongside WEAPON). Open sub-problems for byte-exact MP
authoring: where the console **MAP_ENTS body** comes from (PC has no MAP_ENTS asset — likely synthesized
from the PC map's entity string/rawfile) and what the **duplicate SOUND** references. Order-derivation +
mode-specific insert set is the deliverable; the MAP_ENTS/SOUND body synthesis is the remaining task-#1 work.

### MAP_ENTS resolved (cheap, NOT a rabbit hole) — 2026-07-07
MapEnts body = 36 bytes: name@0 (str), entityString@4 (str), numEntityChars@8, MapTriggers@12 (24B:
models/hulls/slabs small arrays). Load order: body, name str, entityString (numEntityChars bytes),
MapTriggers. **Source already present:** the entity string is inline in the PC clipMap's mapEnts
(clipmap_probe parses "mapEnts inline (N entity chars)") and is byte-identical PC↔console (verified:
raid PC & console both 1508 classnames, same text). **v1 build path:** MapEnts = real entityString
(extract from PC clipMap) + **zeroed MapTriggers** (count 0) — the world renders from GfxWorld, so
triggers/spawns aren't needed for a first render test; full MapTriggers conversion is playability polish.
The duplicate **SOUND** insert is a trivial ref. Net: task #1 is build-viable-scoped; the real remaining
work is task #2 (region generators).

## Task #2 (region generators) — QUANTIFIED (2026-07-07), less scary than feared
Measured the raid GfxWorld (22.25MB): 48% PC-convertible today, 52% (11.5MB) needs a generator. But
the 11.5MB decomposes into three very different buckets:
- **~7.2MB = GX2 textures** — draw.reflectionProbes (5.0MB, cubemaps), draw.lightmaps (1.57MB),
  outdoorImage (0.26MB), tail material inline (0.26MB). These are IMAGE data and the ipak/GX2 image
  pipeline (`ipak_stream`) ALREADY exists and is byte-exact (mp_la 287/287). PC source = inline PC
  images in each region; conversion = DXT→GX2 tiling via the existing image path. Not a new unknown.
- **~4.2MB = PC-sourced, needs converter wiring** — dpvs.smodelDrawInsts (3.69MB; walk-validated,
  modelAliasOK 85/85 — needs a field converter like conv_surface, incl. lmapVertexInfo), materialMemory
  (0.32MB; inline materials, have PC source), cells (0.20MB; PC portals/aabbTrees). Bounded conversion.
- **~0.09MB = genuinely NEW console-only synthesis** — streamInfo.aabbTrees/leafRefs (77KB),
  dpvs.sortedSurfIndex (10KB, a console sort reorder), dpvs.smodelCastsShadow (5KB). Tiny.
So the true frontier unknown is ~90KB, not 11MB. Priority: (1) wire smodelDrawInsts converter (biggest
non-image chunk), (2) route the 4 GX2-texture regions through ipak_stream, (3) synthesize the ~90KB
console-only bits. `convert_region` returns None for method in {reorder_pc, console_gx2, reuse, gen} and
fields-without-swap — those are the ones to fill.

### CUBEMAP GX2 PATH VERIFIED (2026-07-07) — the soft spot, closed positively
Guard: the ipak/gx2 pipeline was validated on 2D map textures (mp_la 287/287); reflection-probe
cubemaps (5.0MB, the biggest GX2 chunk) are a different layout (6 faces + mips). VERIFIED: extracted a
genuine console raid probe cubemap (dim=3 CUBE, 128x128, 6 faces, 8 mips, BC3/0x33, **tileMode=4**
which gx2_texture supports). `gx2_texture.detile`/`tile` already take a **`slice_index`** param for
array/cube faces; round-trip (detile->tile==identity) is **byte-exact 6/6 faces**. Each face level0 =
16384B = one `surface_info` size; cube = 6 stacked 2D face surfaces. So probe cubemap PC->console =
per-face `tile()` + GX2 header synth (the existing gfximage/ipak path), NO new tiling algorithm. The
5MB bucket is confirmed existing-pipeline territory. (Remaining wiring: the per-face loop + probe/
material GX2 header synthesis; "tail material inline" is a GX2 material body, same image machinery.)

### smodelDrawInsts (task #2 biggest non-image, 3.69MB) — structural repack, the real bounded work
GfxStaticModelDrawInst: console **208B**, PC **152B** (NOT a simple swap). Field map (console:PC offset):
cullDist@0, placement@4 [console 4..32 = **28B GfxPackedPlacement** vs PC 4..56 = **52B GfxPlacement** —
axis matrix packed on console], model@(32:56), flags@(36:60), invScaleSq@(40:64), lightingHandle@(44:68),
colorsIndex u16@(46:70), lightingSH@(48:72), primaryLightIndex u8@(72:96), visibility@(73:97),
reflectionProbeIndex@(74:98), smid@(76:100), lmapVertexInfo[4]@(80:104) each (**32B console : 12B PC**).
Two real conversions: (a) placement 52->28 packing (matrix->packed, need console encoding), (b)
lmapVertexInfo 12->32 expansion + trailing lmapVertexColors (walk already parses these, 2052 FOLLOW on
mp_skate). Bounded but non-trivial — this is the next build step. For a first render test, a zeroed/
stubbed smodelDrawInsts (static props absent, base world still renders from GfxWorld surfaces/vd0) is a
fallback if placement packing resists, same stub-and-test logic as MAP_ENTS.

## Track G container authoring — foundation VALIDATED (2026-07-07)
Implemented + validated the no-backbone container pieces (`native_linker/_assetlist_author.py`):
- **Asset-array type remap: byte-exact.** `pc_to_console_type` (invert console_to_pc; MAP_ENTS name-
  disambiguated) reproduces the genuine console asset types with **0 mismatches on aligned assets** —
  raid 886/886, dockside 799/799. The only residual is the mode-specific inserts (MP: +MAP_ENTS,
  +SOUND).
- **String table: IDENTICAL PC↔console** (raid 565==565, zero diff) — reuse verbatim, no authoring.
- Container layout (from `wiiu_zone`): header[40] (size, externalSize, blockSize[8]) → XAssetList[24]
  (stringCount, strings_p, dependCount, depends_p, assetCount, assets_p) → string ptr array (count×u32
  FOLLOW/null) → inline strings → asset array (count×{u32 type, u32 headerPtr}) → block-5 bodies.
So the container shell is authored: string table verbatim + asset array via validated remap + the
MP insert set. Remaining container work = the per-asset headerPtr (FOLLOW/alias via omap) and block
sizes, both computed during body emission.

## Assemble (task #3)
PC asset list -> console list (#1) + string table + block layout (ZoneWriter) -> author each body via
the converters above (+ #2 generators) -> emit v148 BE container -> pack (`WiiU_FF_Studio/wiiu_ff.pack`
or `tools/ff_pack.py`) + sign-patch. First goal: a build-ATTEMPT artifact that surfaces concrete gaps,
not necessarily a boot.

## Assemble loop STARTED + raid-oracle control operational (2026-07-07) — surfaced a real gap
`native_linker/produce_nobackbone.py` — the assemble loop. `walk_pc_bodies(PC)` yields per-asset
console-bound spans via the Track E dispatch; on raid the spans are **contiguous & monotonic (gaps=0)**
= clean emit order. Raid-oracle control: pair PC bodies to genuine console bodies (ReEmitter round-trip,
covers assets 0–~850 before the console-walker limit) by (name, occ), emit via converter, diff.

**FINDING (the control earned its keep): `convert_xmodel` under-emits.** XModel size-match vs oracle =
**125/369** (71 skinned correctly allowlisted/raise). The rest produce WRONG-SIZED bodies (e.g. 15KB vs
genuine 1.5MB) — `convert_xmodel` emits material *handles* but NOT the inline-material **GX2 image
pixels** (the "image track" left undone), so those bodies are truncated. A truncated body corrupts the
zone stream (loader reads into the next asset) → **not loadable**, not merely byte-different. This is a
loadability gap, NOT an allowlist item.

**Impact on mp_skate build (critical-path revision):** mp_skate has **466 inline XModels, 0 aliased**
(more than raid) — fully exposed. Stubbing smodelDrawInsts does NOT help: the XModel asset bodies must
still be correctly-sized/loadable in the stream regardless of whether they're drawn. So **completing
`convert_xmodel`'s inline-material GX2-image emission is now a prerequisite for a loadable mp_skate zone**
— the concrete next build item the raid control named. Good news: the inline images are the SAME GX2
machinery already verified (incl. cubemaps 6/6); this is wiring the image pipeline into convert_xmodel's
inline-material path, bounded work. (Also re-check the smaller size diffs for any true machinery bug vs
documented lossy regions before trusting the rest of the allowlist.)

## XModel loadability gap CLOSED (2026-07-07, same session) — collmaps + inline images built
The two unbuilt XModel regions the raid control named are now BUILT and validated:
- **collmaps chain** (`xmodel_convert.convert_xmodel_collmaps`): Collmap(4)→PhysGeomList(12)→
  PhysGeomInfo(68)×n→BrushWrapper(96)→sides(12×n, each FOLLOW side carries an INLINE cplane_s(20) —
  the initially-missed piece, found by diffing vs the end-to-end-proven `xmodel_pc._collmaps_span`)
  →verts(12×n)→planes(20×n, last word verbatim). All identical-layout PC↔console (OAT fills have no
  SwapEndianness branches) → structural swap + ptr reloc. Span-check vs the independent PC walker:
  **0 mismatches** (459 skate / 437 raid).
- **inline-material GX2 images** (`material_convert.convert_image`, wired into convert_material's
  texture loop): PC 80-B GfxImage body (name@72, loadDef@0: fmt@4, resourceSize@8, pixels@12) →
  console 328-B GX2 body + name + tiled pixels via the ALREADY-VALIDATED `ipak_stream.build_inline_body`
  (gx2 tile path). PC-streamed images (resourceSize=0) → console streaming body (no inline pixels;
  resolve from .ipak at runtime by hash). Guard: convert_image's consumed span is cross-checked against
  the proven `pc_image_span`; on disagreement, falls back to consume-and-skip (streamed body).

**Validation — the right bar.** Genuine byte/size parity is NOT the loadability bar (residual genuine
size deltas remain: a -16/-32 class not yet root-caused, low-bit lossy float diffs in bonedata,
memUsage@204, and PC-streamed→console-inlined pixel cases where genuine inlines 1.5MB we emit as
streaming). The loadability bar is **self-consistency**: re-walking MY emitted bytes with the proven
console-side parser (BR.ReEmitter over the emitted buffer) must consume exactly len(emitted).
Result: **raid 437/437 ok, mp_skate 459/459 ok, 0 bad.** Every non-skinned XModel on both maps now
emits a stream-valid console body. Remaining XModel items: 7 skinned on mp_skate (plan: emit-rigid +
OAT_NO_SKIN loader-tolerance test), and the streamed-fallback boot-risk note (image pixels must be in
the map .ipak — which the pipeline builds from PC sources anyway).

## Assemble loop RUNS + skinned emit-rigid CLOSED (2026-07-07 late) — coverage measured
**STEP 1 done:** `convert_surface_header(force_rigid=True)` + skinned-blob consumption in
`convert_xmodel_surfaces` (sizes from the proven xmodel_pc walk: vertsBlend=(n0+3n1+5n2+7n3)*2,
tension=Σn*4, pre-verts0). **mp_skate 466/466, raid 440/440** — emit + span-exact + console-rewalk
self-consistent. XModel is CLOSED. The 7 skinned identified (CAVEATS §1 updated): 2 named fxanim props
(ferris wheel, teardrop flag) + 4 alias-named siblings + german_shepherd — all ambient/scorestreak;
**emit-rigid permanent for mp_skate MP**.

**STEP 2 skeleton RUNS:** `produce_nobackbone.assemble_zone(pc_path)` — body-emission loop in authored
order with per-type coverage + asset-granular `Omap` (start-exact; interior linear, exact for same-size
swaps, APPROX counted for size-changing; unresolved counted → fatal once coverage complete).
mp_skate result: **emitted 27.3MB / 495 assets** (XModel 24.9MB, clipMap 2.1MB, GameWorldMp, StringTable,
ScriptParseTree, Footstep, ComWorld, Material, RawFile, GfxImage, KVP). **Named remaining gaps:**
- MaterialTechniqueSet ×245 — WIRING ONLY (Track B corpus blob by name; corpus + manifest exist)
- FxEffectDef ×79 — needs the full FX converter (fx_convert has header only; elems 292B are
  layout-identical → structural swap + visuals/strings, bounded)
- XAnimParts ×7, DestructibleDef ×2, GfxLightDef ×2, Glasses ×1, PhysPreset ×2 (trivial — reuse
  xmodel's physpreset emit), SkinnedVertsDef ×1 — small converters
- SndBank ×1 (49.8MB PC-side) — biggest unknown left in the loop
- GfxWorld ×1 — the Track F generators session (stubs acceptable per split)
**Omap risk measured on mp_skate:** interior_approx=2613 (aliases into size-changing types — drive down
with per-chunk region maps or verify targets), unresolved=1178 (expected while types are missing —
becomes the FATAL assert once coverage is complete). Next: wire techset blobs (biggest single win,
245 assets/49MB PC-side), then FX, then the smalls, then container+pack.

## Techset wiring DONE + SndBank scoped (2026-07-09)
**Techsets ×245 CLOSED:** `assemble_zone` now looks up each inline techset by body offset
(`TT.pc_techset_names_walk` pairs) → manifest (`wiiu_ref/techset_corpus/mp_skate_subst.json`,
REGENERATED with the fixed walk: **245/245, 0 unresolved** — the old 241 manifest predated the Track E
walk fixes; emit_manifest does NOT auto-save, json.dump it) → corpus blob (self-contained console
bytes, zero-alias selfchecked). mp_skate coverage now **61.5MB emitted** (techsets 34.2MB + XModel
24.9MB + the rest). Omap: unresolved 1178→712 as coverage grows (as predicted).

**SndBank ×1 (49.8MB) — NOT a byte-copy, but bounded:** verified vs the raid console oracle
(PC @0x5bcd226-ish, console @0x45c04a5): the interior sound BLOB is **verbatim-identical at identical
relative offsets** (size-identical layout), but the ~100KB head is mixed-width tables (u32/u16/u8/
strings/aliases — word-swap classification shows structured 'x' regions, not clean swap4). Conversion
= field-aware swap of the head mirroring `sndbank_pc`'s known layout + verbatim blob copy. Next
session's first item alongside FX.

**Remaining to first artifact (updated):** FX ×79, SndBank ×1 (field-aware head swap), XAnim ×7 +
smalls (Destructible ×2, GfxLightDef ×2, Glasses ×1, PhysPreset ×2, SkinnedVerts ×1), GfxWorld ×1
(Track F session/stub), then container+pack. **Gate before boot (per review): the raid-oracle control
must adjudicate the 3079 interior_approx omap relocations** — self-consistency validates sizes, NOT
pointer values; a wrong interior target is a silent message-less Sys_Error (CAVEATS §9). Drive
unresolved→0 (fatal assert) once coverage completes.

## Caveat carried from the walk work
raid + mp_skate both reached end-of-zone WITHOUT exercising WEAPON (skate aliases weapons from
common_mp; raid has none). So the build path for mp_skate is fully walked, but the first *zombies*
build will still need the WEAPON consumer (queued as the next dispatcher item; see
`FINDINGS_gfxworld_localization_diag.md`). WEAPON is NOT on the mp_skate build critical path.
