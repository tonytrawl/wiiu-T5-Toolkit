# HANDOFF — native PC→console converters (everything except vd0 geometry)

Goal: let the native pipeline convert a **no-backbone** PC map (e.g. mp_skate DLC) into a
**loadable** Wii U .ff — i.e. stop depending on a genuine console zone to supply the complex
assets. vd0 world geometry is tracked separately in `HANDOFF_geometry_vd0.md` (in progress); do
NOT duplicate it here. This doc covers the other roadblocks, split into parallelizable tracks for
multiple sessions.

Orchestrator that consumes all of this: `native_linker/pc_convert_pipeline.py` (`convert_zone`).
Today `convert_zone` requires a genuine console backbone; the end state is that it assembles a
console zone from PC alone. Each track below plugs a converter into that assembly.

Ground rules (all sessions):
- Validate every converter against the genuine console **oracle**: convert the PC body →
  must equal the genuine console body byte-for-byte (`native_linker/validate_pc_convert.py` is the
  pattern; mp_raid has both PC + console zones). Byte-exact vs oracle = done.
- struct_layout is right for simple/material-class structs but WRONG for GfxWorld draw onward and
  some vec typedefs — cross-check with `wiiu_ref/gfxworld_probe2.py` landmarks where relevant.
- Never edit files under `E:\...` — copy out first.
- Pointer encoding: `(block<<29 | offset&0x1FFFFFFF)+1`; FOLLOW=0xFFFFFFFF, INSERT=0xFFFFFFFE,
  null=0; block-5 (VIRTUAL) offset = stream offset − 64. Relocation is via the omap (see
  `pc_to_console.PCConverter`).

---

## Dependency order (read first)
```
  TRACK E (walker byte-exact on complex types)  ── prerequisite for native no-backbone traversal
        │
        ├── TRACK A (Material)      ← smallest, do first, proves the pattern
        ├── TRACK C (XModel)
        ├── TRACK D (FX / FxEffectDef)
        └── TRACK B (Techset substitution)   ← independent of E for the substitution approach
  TRACK F (GfxWorld non-geom synthesis)  ── depends on A/B/C for the assets it references
  TRACK G (integration)  ── last; wires converters into convert_zone for no-backbone assembly
```
A, B, C, D can proceed in parallel once E is understood. B (substitution) can start immediately.

---

## TRACK A — Material PC→console converter  ✅ BUILT & VALIDATED (2026-07-06)
**Status:** DONE for shared materials. `native_linker/material_convert.py` (converter) +
`native_linker/validate_material.py` (matched-pair oracle). **437/446 real shared materials convert
BYTE-EXACT vs genuine console; 446/446 round-trip.**

**CORRECTION to the old note:** Material is NOT "112 B both platforms / trivial byte-swap". The
console struct is **104 B** (PC is 112 B) with real layout divergences, and **mp_raid has ZERO
Material assets** — they live in `common_mp` (map zones alias them). The oracle is
`common_mp.zone` (console) vs `PC ff/common_mp.zone` (PC), joined by info.name string.

**Verified console layout divergences (all reversed from genuine common_mp):**
- `MaterialInfo` 48→40: drops `surfaceFlags` (PC u32 @36) + pad; `contents` (PC @40) moves to
  console @36 and is **copied VERBATIM (NOT byte-swapped)** — a linker quirk (525/0 in the oracle).
  `drawSurf` IS kept (8-byte-swap as packed u64). All other scalars byte-swap normally.
- `stateBitsEntry` char[36]→char[32] (mirrors techset techniques 36→32).
- `GfxStateBits` 20→8: keep loadBits[2], drop 3 D3D state-object pointers (ZoneCode cond=never).
- Material total 112→104: counts 84→72, 5 pointers 92→80.  (matches `xmodel_probe.MAT_SIZE=104`
  and `consume_material` offsets.)

**KNOWN GAP:** 9/446 `mc/mtl_*` model materials with non-zero hashIndex/surfaceFlags packing differ
in 2 bytes @ console off 34 — not yet reversed (hashIndex is a sort hash; low impact). And
stateBitsEntry uses a raw 32-slot truncation; the exact PC(36)↔console(32) technique-slot remap is
shared with Track B (needed only if a material's per-technique state indices must be exact).

**Integration TODO (Track G):** `convert_material(pc, off, reloc)` takes a `reloc(pc_ptr)->co_ptr`
callback for alias relocation (default identity for tests) — wire it to the omap. Inline
image/techset/thermal (FOLLOW sub-assets, common in common_mp UI materials) are Track C/B and are
NOT emitted here; the pipeline must dispatch those. `validate_material.is_pure`-style detection
distinguishes alias-only ("pure", Track A) from inline-asset materials.

**BONUS FIX (unblocks common_mp on both sides):** the asset-list array is **NOT 4-aligned** — it
immediately follows the inline string table. `wiiu_zone.py` and `pc_zone.py` had a spurious
`(o+3)&~3` that corrupted every common_mp parse (mp_raid happened to land aligned). Removed.
common_mp console now parses 6272 assets incl. 496 materials; PC parses too.

---

## TRACK B — Techset PC→console (translation/substitution layer)
**The question posed:** "use existing known techsets" vs "a better way."
**Answer:** substitution IS the right pragmatic path. True D3D11→GX2 shader **recompilation** is the
"better" way in principle but is a large compiler project (recompile HLSL/DXBC → Latte GX2 ISA) and
not worth it now. Substitution gets a loadable, correctly-rendering map for every shader that has a
genuine console equivalent — which for BO2 is most of them, because techsets are largely shared
engine shaders living in `common_mp` (on Wii U), not per-map.

**Prototype already exists:** `wiiu_ref/techset_extract.py` extracts genuine console techsets as
self-contained blobs (alias-resolved) — 301 raid blobs in `wiiu_ref/techsets_raid/`. This is the
substitution primitive.

**Do (build the translation layer):**
1. **Corpus:** extract genuine console techset blobs from every console zone available
   (`common_mp.zone`, `mp_raid_genuine.zone`, `zm_transit_original.zone`, any DLC console zones) →
   a name→blob library. Techset names are the join key and are platform-independent.
2. **Match:** for each PC techset in the target map, look up the same name in the corpus. Exact-name
   hit → substitute the genuine console blob verbatim (`OAT_TECHSET_DIR`-style, or the native inline
   equivalent). This covers all shared/common techsets.
3. **Fallback for map-unique techsets with no corpus match:** map by *shader signature* instead of
   name — group console techsets by (vertexDecl layout, technique count, pass semantics) and pick a
   compatible one. A visually-approximate but structurally-valid shader loads and renders; exactness
   is cosmetic. Record misses so the coverage is honest.
4. Report coverage per map (matched / signature-substituted / unmatched).

**Files:** `wiiu_ref/techset_extract.py`, `wiiu_ref/shader_probe.py`, new `techset_translate.py`.
**Done when:** for mp_skate, ≥ the common-shader fraction substitutes by exact name and the rest map
by signature; no dangling shader refs. **Gotcha:** techsets alias shared subobjects (techniques,
vertexDecls, literal consts) — the extractor already resolves these; keep that invariant (every
emitted blob must contain zero alias pointers, re-parse-verified).

---

## TRACK C — XModel PC→console converter  🟡 BODY DONE, surfaces WIP (2026-07-06)
**BODY converter BUILT & VALIDATED:** `native_linker/xmodel_convert.py` (`convert_xmodel_body`) +
`native_linker/validate_xmodel.py` (matched-pair oracle on common_mp, 465 pairs). **452/465 XModel
bodies convert BYTE-EXACT** (masking relocated pointers + the 2 computed fields below). The 13
fails are `t6_wpn_*_view` viewmodels whose LOD-dist / radius / mins **floats genuinely differ**
between PC and console content (not a converter bug).

**Body layout (verified, 248→244):** PC-identical through +208; PC `bool bad`@212(+3 pad) DROPPED,
tail shifts −4. All fields byte-swap / u16-swap / pointer-relocate EXCEPT:
- **lightingOriginOffset vec3 + lightingOriginRange (last 16 B)** copied **VERBATIM, not byte-swapped**
  (465/0 — same linker quirk as Material `contents`).
- **himipInvSqRadii ptr @200**: PC null, console FOLLOW → console GENERATES an inline `numsurfs` f32
  array. NOT a copy; must be synthesized. (`convert_xmodel_body(..., himip=)`.)
- **memUsage @204**: console-computed memory stat, differs from PC. (`memusage=`.)
These two are the ONLY non-PC-derivable body fields.

**BONE-DATA block DONE (2026-07-06):** `convert_xmodel_bonedata` converts the contiguous
name/boneNames/parentList/quats/trans/partClassification/baseMat block (precedes surfaces).
**447/465 byte-exact** vs genuine (validate_xmodel.py); the 18 fails are the same viewmodel/weapon
class as the body — lengths all match, only quats/trans/baseMat float VALUES differ (genuine PC-vs-
console content, not a bug). Per-array behavior verified: boneNames u16-swap, parentList verbatim,
quats s16-swap, trans f32-swap, partClassification verbatim, baseMat f32-swap. `boneInfo` comes
AFTER surfaces so it's deferred with the surface sub-project.

**STILL TODO (the bulk):** the hard part — **XSurface (GX2)** + vertex buffers, then boneInfo/
collSurfs/himip/physPreset/collmaps (post-surface trailing).
**✅ CONSOLE XSurface SIZE PINNED = 128 (2026-07-06):** `struct_layout` says 64 but it is WRONG
again (same as Material 112-vs-104). `xmodel_probe.SURF=128` is CORRECT — confirmed empirically:
`parse_xmodel` walks ns×128-B surface headers + their dynamic data and **byte-exactly resyncs onto
the next XModel body across all 470 common_mp XModels** (multi-surface models ns=2..14 verified). If
it were 64 the walk would desync and `is_body` would fail on every subsequent model. Build the
surface converter on 128, NOT 64. Console XSurface layout notes in
`wiiu_ref/xmodel_probe.py` (parse_surface_dyn); vertex re-encode is `wiiu_ref/latte_vertex.py`
(`pc_vertex_to_console`:
position/uv/color/binormal-sign byte-exact, **normal/tangent lossy ~1-2 quantizer steps — INHERENT**:
PC's 10-bit ThirdBased already lost the precision). So a *fully* byte-exact surface is impossible from
PC alone; positions/uv/color/indices/headers will be exact. Also solve memUsage + himipInvSqRadii.
**Do (original):** byte-swap the XModel body + XModelLodInfo + XSurface headers; run `latte_vertex` on each
surface's vertex/index buffers; relocate all refs (materials [→ Track A], phys, collision).
**⚠️ ORACLE LOCATION DEPENDS ON GAME MODE (verified 2026-07-06):**
- **MP maps** centralize shared assets in **`common_mp`** (6272 assets, 496 materials); map zones are
  thin and *alias* almost everything (mp_raid: 2 models, 2 materials inline). → For an MP model,
  build the oracle as `common_mp.zone` (console) vs `PC ff/common_mp.zone` (PC), joined by name.
- **ZM maps are the OPPOSITE — self-contained.** The zm map zone carries its models/materials
  **inline** (zm_transit: 1392 models, 404 materials; zm_nuked: 1711 models). `common_zm` is small
  (1282 assets) and is NOT the shared store common_mp is. → For a ZM model, the oracle is **the ZM
  map zone itself** (console vs PC), NOT common_zm. (Bonus: a no-backbone ZM map has all its complex
  assets locally, so it doesn't depend on common_zm being converted.)
Use the `validate_material.py` matched-pair (join-by-name) pattern either way. Do NOT blanket
"validate vs mp_raid". Confirm which type-id is XModel empirically (join-by-name coverage) — the WiiU
console type-ids are shifted (console type 6 = Material) and differ from the PC-tool ids.
**Files:** `wiiu_ref/latte_vertex.py`, `native_linker/pc_to_console.py`, `native_linker/validate_material.py` (oracle pattern to copy).
**Gotcha:** XSurface vert/index buffers are GX2 — reuse latte_vertex's tiling/stride logic; confirm
console vertex stride vs PC (models are 24+8, distinct from the 36-B world vert).

---

## TRACK D — FX (FxEffectDef) converter  🟡 HEADER DONE (2026-07-06)
**HEADER converter BUILT & VALIDATED:** `native_linker/fx_convert.py::convert_fx_header` — the 76-B
FxEffectDef header converts **388/388 byte-exact** vs genuine common_mp (matched-pair oracle, join by
name; masking the 2 relocated pointers). Per-field verified: clean byte-swap with the count fields at
u16 granularity (flags@4, elemDefCount* @8/10/12) — **NO verbatim-float quirks** (unlike Material
`contents` / XModel lightingOrigin), and `totalSize`@16 swaps cleanly (388/0) so it is derivable, not
console-computed. Traversal unblocked by `native_linker/fx_pc.py::parse_fx_pc` (Track E).
**REMAINING:** the FxElemDef array (292 B each, also byte-identical layout) + dynamic tail
(velSamples/visSamples curves, visuals, refs). Reuse `parse_fx_pc`'s traversal for extents and the
same per-field swap tally on FxElemDef (over the 388 pairs) to pin its u16/byte/pointer fields before
emitting. Relocate refs (materials, models, sounds). Mostly scalar/curve data — no GX2.
**⚠️ ORACLE LOCATION:** same trap as A/C — FX effects live in **`common_mp`** (+ shared fx zones),
not mp_raid. Build the matched-pair oracle on common_mp joined by effect name (validate_material.py
pattern). Confirm the FxEffectDef type-id empirically.
**Files:** `native_linker/pc_to_console.py`, `native_linker/validate_material.py` (oracle pattern);
needs Track E first for clean traversal.

---

## TRACK E — PC walker byte-exact on complex types  🟡 DISPATCHER + FX PROBE DONE (2026-07-06)
**Status:** the dispatcher reframe is VALIDATED. `native_linker/pc_walk.py` walks a PC MAP zone,
routing FX → the new `native_linker/fx_pc.py` (`parse_fx_pc`, a LE mirror of the console `parse_fx`
— FxEffectDef/FxElemDef are byte-identical in layout across platforms) and everything else to the
generic struct walker, skipping aliased assets (asset-list header ptr != FOLLOW). On PC mp_raid the
FX probe took the clean walk from **51 → 143 assets** (generic-only stalls on the first FX at 51).

**⚠️ TARGET CORRECTION:** validate the WALK on a **MAP zone (mp_raid)**, NOT common_mp. common_mp is
the shared backbone (never converted; a no-backbone map aliases it) and is dominated by menu/weapon/
ANIM assets that lack probes — the *console* dispatcher itself only clears ~120/6272 there. (common_mp
is still the right MATCHED-PAIR ORACLE for Material/XModel per-body validation — different purpose.)

**INLINE-IMAGE SPAN HELPER DONE (2026-07-06):** `material_convert.pc_image_span` — self-validating
(locates the GfxImage body via name-ptr FOLLOW @+56 + `R_HashString(name)==hash@+60`, tolerating the
16-B GfxTexture prefix before a material's inline image; struct_layout's GfxImage offsets are the
wrong variant). **KEY:** after the name the reorder emits `texture.loadDef` = a `GfxImageLoadDef`
(12-B header: levelCount@0/flags@1/format@4/resourceSize@8) + `resourceSize` pixel bytes — so the
span is body(64)+name+12+resourceSize (streamed images have resourceSize=0 → a 12-B tail; this was
the missing piece). Plugged into `convert_material` (best-effort; Track A's 437/446 preserved) and
`fx_pc._material_span`. **Cleared the entire FX block: mp_raid walk now resyncs 51 → 150 assets.**

**PC XMODEL SPAN PARSER DONE (2026-07-06):** `native_linker/xmodel_pc.py::parse_xmodel_pc` — mirrors
console `xmodel_probe.parse_xmodel` in LE with PC sizes (reuses `convert_xmodel_bonedata` for the
body+bones prefix). PC XSurface = 80 B (no verts1/GX2): per surface = verts0(vc×32, present when
`!(flags&1)` & FOLLOW) + vertList(vlc×12 + collision trees) + triIndices(tc×6); then materialHandles
(FOLLOW→inline Material via convert_material), collSurfs(44 + collTris×48), boneInfo(nb×44), himip,
physPreset(84)+strings. Dispatched in `pc_walk.py`. **XModels 150-152 resync byte-clean; walk now at
157.** (span-only, fully separable from console GX2 surface conversion — no vd0 sync.)

**BIG ADVANCE 2026-07-06: mp_raid PC walk now resyncs 767 / 887 assets** (was 51). Fixes this turn:
- **`pc_image_span` made DETERMINISTIC** (was a fragile hash-window scan that failed on dense zones):
  the GfxImage body sits after a fixed lead (0 or 16 B), found by `name-ptr FOLLOW @+56` in a TINY
  window (no hash — hash fails on comma-prefixed ALIASED image names, hash@+60=0). The `texture.loadDef`
  tail (`GfxImageLoadDef` 12-B header @name_end + resourceSize pixels) is emitted **only for REAL inline
  images** (`texture@body+0 != 0`); aliased zeroed stubs (comma name) carry no loadDef. This one fix
  took the walk 155 → 228 (cleared a flood of FX/material inline-image variants).
- **PC collmap span** (`xmodel_pc._collmaps_span`, mirrors console consume_collmaps; PhysGeomList 12/
  PhysGeomInfo 68/BrushWrapper 96/cbrushside 12/cplane 20 — identical PC sizes): 228 → 693.
- **Skinned XSurface** (`xmodel_pc._surface_dyn`): flags&2 → vertsBlend (Σ 1,3,5,7·vertCount[j], u16)
  + tensionData (Σ vertCount, f32) before verts0: 693 → 723.
- **DestructibleDef** dispatched to `destructibledef_probe.parse_destructible(d, off, '<')` (it already
  takes an endian arg): 723 → 767.

**CURRENT DRIFT (asset ~766, TECHNIQUE_SET):** left to the GENERIC walker (its ZoneCode walk handles
most techsets incl. inline DXBC shaders → reaches 767); it under-reads a late techset and the null-
heavy tail hid the drift behind next=0, so `@0x26de9a4` is a mis-aligned start (a technique-name
string sits mid-"body").

**`native_linker/techset_pc.py`** (`parse_techset_pc`) — deterministic PC techset span, DISPATCHED in
pc_walk (reaches 767, matching the generic walker). Emission order taken from the OAT codegen (ground
truth, not byte-reversed): `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/materialtechniqueset/
materialtechniqueset_t6_write_db.cpp`:
- MaterialTechniqueSet=152 (name@0 str, worldVertFormat@4, techniques[**36** slots]@8, console 32) →
  name string → per FOLLOW slot: MaterialTechnique.
- MaterialTechnique = 8 hdr (name@0,flags@4,passCount@6) + passArray[passCount]×24 (contiguous) →
  per pass IN ORDER **vertexShader, vertexDecl(116), pixelShader, args** → technique name string LAST.
- Material{Vertex,Pixel}Shader = 16 body (name@0 str, program ptr@8, programSize@12) + name string +
  programSize DXBC bytecode (Align(1)=byte-packed). args = MaterialShaderArgument×Σargc (12 B; type@0,
  u@8); type LITERAL_VERTEX/PIXEL_CONST (1/7) + u.literalConst@8 FOLLOW → +16 (float[4]).
- **KEY: technique-tree elements are STREAM-PACKED — NO alignment between them** (the codegen's Align
  is per-block; invisible in absolute offsets). Confirmed on "effect_w77q49e8": vShader(DXBC 0x2534) →
  vDecl(116) → pShader(DXBC 0x1fa4) pack contiguously.
- **NOTE for Track B:** PC techsets carry INLINE D3D DXBC shaders (not aliased refs) — this parser is
  exactly what LOCATES them; substitution reuses it instead of rediscovering the shader-locating logic.

**MAJOR PROGRESS 2026-07-06 (session 2): PC map-zone walk now resyncs 852 / 887 assets** (was 51).
The "2-byte destructible" diagnosis from session 1 was WRONG (miscounted the boundary). ROOT CAUSE via
the console oracle: DestructibleDef 747 has **inline PhysConstraints** in pieces 7 & 8 (physConstraints
@piece+268 = FOLLOW) that `parse_destructible` never consumed (it only handled damageSound/burnSound).
Fixed `destructibledef_probe.parse_destructible` to consume the full per-piece dynamic in codegen order
(stages' strings, physConstraints@268 [2696 body + name + 16×(target_bone1/2)], damageSound@276,
burnEffect@280, burnSound@284). Console round-trip still byte-identical (the console destructible also
has inline physConstraints — the fix helped both). This unmasked a cascade of further world-block
under-reads, all now dispatched (PC-side, read-only where noted):
- **GfxLightDef** -> `lightdef_pc.py` (body16 + name + inline attenuation cookie GfxImage via pc_image_span)
- **GfxWorld** -> `gfxworld_pc.py` (delegates to geometry session's `gfxworld_probe2` 'pc' cfg READ-ONLY;
  its PC walk is ~788 B short of the tail, so bridges to GameWorldMp's own signature for the true end)
- **GameWorldMp** -> `gameworldmp_probe.Walker(d,'<',144)`
- **Glasses** -> `glasses_pc.py` (glasses[n]×140 + inline GlassDef: name + pristine/cracked/shard Material
  [convert_material] + 3 sounds + crack/shatterEffect [parse_fx_pc])
- **clipMap_t** -> `clipmap_pc.py` (reuses `clipmap_probe.walk` — parameterised it for endian, default '>'
  backward-compatible; clipMap is PC-identical 332-B body)
- **Material** (top-level) -> `material_convert.convert_material`; extended pc_image_span for NULL-name
  streamed images (body 64 + loadDef 12+resourceSize).

**COMPASS IMAGE SOLVED (2026-07-07):** the NULL-name streamed inline image (top-level material texture)
= body(64) + **streamedPartCount×8** (GfxStreamedPartInfo; streamedPartCount is the BYTE @27 — pinned
empirically; struct_layout GfxImage is the wrong variant, offsets don't apply) + GfxImageLoadDef(12 hdr +
resourceSize, =0 for streamed). Console INLINES the 262144 px (baseSize@160, pixels@176); PC streams
them via ipak. Fixed in `material_convert.pc_image_span` (null-name path) + validated: every raid
material-inline image resyncs (the walk reaching 870 IS the cross-image validation). Track A still 437.

**CURRENT DRIFT — SOUND 870 (SndBank), NOT XANIMPARTS (that was masked):** with compass fixed the walk
reaches asset 870; SOUND/SndBank (4768-B body, complex: aliases/radverbs/ducks/asset-banks) under-reads
under the generic walker, and its next=0 masked it (XANIMPARTS 871's null-name start was the symptom, not
the cause — 0x5ced31d is mid-sound-data, sound alias "prj_bullet_impact_large_carpet" nearby). The console
`wiiu_ref/sndbank_probe.parse_sndbank(d,b,'<')` OVER-reads to ~EOF on PC (PC SndBank layout differs) — so
SndBank needs PC-specific span work, not a drop-in dispatch. **The tail has MORE new types than expected:
SndBank → XAnimParts (×2; `xanimparts_probe.parse_xanim(d,b,'<')` is endian-ready) → FootstepTable (×7)
→ IMAGE (×6, top-level).** NEXT: crack SndBank PC span (oracle: console_sndbank_sample.bin + mp_raid
console SndBank), then the ready xanim/footstep/image dispatches → end-of-zone. Expanded past the "one
XANIMPARTS" estimate, so checkpointed here per plan (walk crash-guarded; oracle notes captured).

**STRATEGIC (scope the SndBank work — it's smaller than it looks):** SEPARATE the two needs.
(1) TRACK E / the WALK needs only SndBank's SPAN — you can't skip an asset mid-stream, you need its
extent to resync. Bounded matched-pair-oracle task: raid has SndBank on both platforms (+ captured
console_sndbank_sample.bin). Diff PC vs console to find WHY parse_sndbank over-reads on PC — it's the
usual count-width / dropped-field divergence (same class as Material 112→104 / XModel bad-drop). Build
`parse_sndbank_pc` for the SPAN ONLY, nothing more.
(2) The eventual no-backbone ASSEMBLE almost certainly does NOT need real SndBank conversion — a map
boots+renders without valid soundbanks. So do NOT build a byte-perfect SndBank converter now; a
stub/minimal SndBank at assemble time is likely fine for first boot (CONFIRM when there: does a map
load with an empty/stub SndBank?). This takes the hard part of SndBank off the critical path.
So next-session scope = PC SndBank SPAN parser → the 3 ready dispatches (XAnimParts endian-ready,
FootstepTable [SIMPLE], IMAGE) → end-of-zone milestone. Explicitly NOT a perfect sound converter.
Then the nuketown + zm acceptance run (distinct validation phase / session boundary).

**New PC-dispatch modules (native_linker/):** lightdef_pc, gfxworld_pc, gameworldmp (probe reuse),
glasses_pc, clipmap_pc, techset_pc, xmodel_pc, fx_pc — all wired in `pc_walk.py`. Debug tool: the strong
per-type resync loop (validate next asset is a plausible body for its type; ALLOW 0-surf tag XModels,
0-elem FX, aliased/null names) — it finds each true under-read behind weak next-word resyncs.
**Then re-run the walk on mp_nuketown_2020 + a zm map (zm_transit/zm_nuked) — ZM zones are fat/self-
contained and are the real general-case acceptance test (the alignment bug once hid because mp_raid
happened to land aligned).**

**Prior edits:** removed dead `or True` @ line ~318; gs() guards `CONSOLE_FIELD_ARR` on `self.L.console`.
**⚡ REFRAME (E is smaller than first written):** don't rewrite the generic struct walker. The
Track A/C work already produced **validated per-type walkers that resync byte-exactly across all of
common_mp**: `xmodel_probe.parse_xmodel` (resyncs across 470 models, multi-surface), Material's
`consume_material`, and `pc_image_enum`/`scan_genuine_bodies` for images. Those ARE working extent
oracles for XModel/Material/Image. So E = **a dispatcher**: for each asset, route complex types to
their proven probe to get the exact body span, and only fall back to the generic struct walk for the
types that still lack a probe. The only complex type with NO probe yet is **FX (Track D)** (+ verify
GameWorldMp) — so the genuinely-new work is one landmark-scanner for FX, not a from-scratch walker.
**Do:** build the per-type dispatch in the PC walk; reuse the existing probes as the extent source;
for FX, follow the self-validating-landmark model (`pc_image_enum` style: name-ptr FOLLOW + hash /
known trailing markers) rather than field-by-field size accumulation. Re-validate after each type
that the console round-trip stays byte-identical.
**Files:** `wiiu_ref/walker.py`, `wiiu_ref/struct_layout.py`.
**⚠️ Test on `common_mp`, not mp_raid** — mp_raid has ~zero XModel/Material/FX; common_mp is where
the complex types actually live (6272 assets incl. 496 materials). Also depends on the Track A
asset-list alignment fix (spurious `(o+3)&~3` removed) to parse common_mp at all.
**Done when:** walking the PC common_mp zone yields the same per-asset extents as the console
round-trip for FX/XMODEL/MATERIAL, and the console round-trip is still byte-identical.

---

## TRACK F — GfxWorld non-geometry synthesis (novel map, no backbone)
**Status:** body + all dynamics converters are HW-confirmed for a map WITH a backbone
(`gfxworld_body.py`, `gfxworld_dynamics.py`, `gfxworld_assemble.py`). The console-ONLY regions
(currently `reuse`/`gen` in `REGION_SPEC`) need real generators for a novel map: `streamInfo.aabbTrees`,
`streamInfo.leafRefs`, `cells` (+ portals), `materialMemory`, `dpvs.smodelDrawInsts` (lmapVertexInfo),
`sunLight`, occluders. lightGrid coeffs already = uint16 swap (not a re-bake).
**Do:** generate each console-only region from PC source / defaults (see `gfxworld_dynamics.py`
docstring per-region notes). This is separate from vd0 (Track = geometry handoff).
**Gotcha:** don't confuse with vd0; these are the surrounding DPVS/stream tables, not the vertex data.

---

## TRACK G — Integration (LAST)
Wire A–F into `native_linker/pc_convert_pipeline.py::convert_zone` so that when **no console_ref**
is supplied it still assembles a full console zone: walk PC (E) → per-asset dispatch to the native
converter (A/C/D/B for techsets/materials, world set, image via ipak, GfxWorld via F + vd0) →
emit via `zone_stream.ZoneWriter` (the from-scratch linker, already round-trips byte-identical) →
pack. Then the GUI "PC Fastfile → Wii U + IPAK" button produces a loadable ff for no-backbone maps.
**Done when:** mp_skate (no backbone) produces a .ff that boots in Cemu (geometry may be warped
until vd0 lands — that's expected and acceptable per the user).

---

## Quick-reference facts
- Material: 112 B both platforms, byte-swap + 5 ptrs + MaterialInfo, NO GX2 inline (Track A trivial).
- Techsets are mostly shared engine shaders in `common_mp` (on Wii U) → high substitution coverage.
- Console corpus zones for substitution: `wiiu_ref/mp_raid_genuine.zone`, `common_mp.zone`,
  `zm_transit_original.zone`, `wiiu_ref/Original FF/*.zone`.
- The from-scratch linker (`native_linker/zone_stream.py` + `stage1_roundtrip.py`) already emits a
  console zone byte-identical to genuine — the emit side is solved; these tracks feed it PC-sourced
  bodies instead of genuine ones.

## ⚠️ CLARITY TAG — what OAT is and is NOT (read before citing it)
OAT (`tools/ref_oat`, the extended OpenAssetTools) is a **struct-layout re-emit reference ONLY**.
Use it to sanity-check that a native converter's *bytes* match OAT's for a given asset struct. Do
NOT treat any OAT output as a working target.

**OAT has NEVER produced a bootable Wii U .ff.** Be precise about this so a session doesn't chase a
phantom:
- `dust2_wiiu.ff` **decrypts to a valid v148 zone but was never confirmed to boot or render.** It is
  NOT proof OAT "works end to end" — citing it as a success is wrong. It only proves OAT can emit a
  console-format container.
- The entire native pivot happened **because OAT crashes on load** — it leaves dangling world-asset
  pointers (GfxWorld/GameWorldMp/ClipMap cross-refs), which is exactly what `native_linker` was built
  to fix by emitting every pointer by construction.
- Where OAT falls short, concretely:
  1. **Pointer/alias relocation across assets** — OAT's per-asset write path doesn't reconcile shared
     block-5 aliases, so world assets dangle (the load crash). Native linker solves this via the omap.
  2. **GfxWorld** — OAT has no console-only gump/lightmap/DPVS synthesis; its "solution" is the genuine
     transplant (`OAT_GFXWORLD_FILE` inlines a genuine blob) — a raid null-test, **not** a converter.
  3. **Techsets** — OAT's write path emits **null shader subtrees** (D3D11→GX2 is not transcoded); the
     only working shaders come from substituting genuine console blobs (`OAT_TECHSET_DIR`). Same
     limitation Track B addresses natively.
  4. **Geometry vd0** — unsolved everywhere, OAT included.

**Bottom line:** OAT converts individual struct *layouts* (useful as a byte oracle for Tracks A/C/D),
but it produces neither a bootable ff nor the cross-asset/world/shader/geometry work these tracks
require. Validate native output against OAT's *per-struct bytes*, never against a claim that OAT
"already made a working map."
