# PROJECT STATE — PC → Wii U (T6 / Black Ops II) map conversion

_Master current-state doc. Last full pass: 2026-07-07; current-state header refreshed 2026-07-11
(see LATEST section). This is the top-level index; per-area detail lives in the `HANDOFF_*` /
`FINDINGS_*` docs and the memory files listed at the bottom._

## Goal
Convert a **PC (Plutonium/T6) map fastfile** into a **bootable Wii U (v148) fastfile + ipak**, fully
from PC source — no genuine console backbone required (a "no-backbone" build). Target map:
**mp_skate** (a PC-only DLC map that never shipped on Wii U).

## ⭐⭐ LATEST — ROOT CAUSE FOUND via raid control test (2026-07-11, supersedes everything below)
The two sections below (skate boot-iteration, artifact) are the ground the work stands on, but the
**current state and next action** are here. Full detail: `HANDOFF_raid_control_status.md` +
`HANDOFF_xmodel_inline_image.md` (repo root), memory `pipeline-fails-raid-control`.

**Timeline since the artifact:**
1. **Skate loads → links → into map-init**, then crashed. Calibrated the console runtime band from a
   full-memory crash dump (self-bootstrapping). Rebuilt clean (unresolved 0, roundtrip PASS).
2. **Skate crash diagnosed by disassembly:** NOT the "misaligned field / 0x0308001f" the boot-iteration
   doc guessed (that value is a red-herring stale register). It's a **guest NULL-string deref in a
   `char==','` CSV/StringTable parser** (`movzx ebx,[r13+rdx]`, rdx=0). Chasing it blind was hard —
   no console reference for skate.
3. **PIVOT — raid control test (the key move):** authored a STOCK map (raid) through the SAME from-PC
   pipeline (`produce_container.py raid_dryrun`) — raid has a genuine console zone as ground truth.
   **Authored raid ALSO crashes** (dump 25192, Cemu GPU/recompiler wild-pointer) → the boot failure is
   **pipeline-wide, NOT skate-specific.**
4. **Harness validated:** genuine raid, packed through our packer + deployed via the UPDATE partition
   (`mlc01/.../0005000e/1010cf00/content/english/mp_raid.ff`, overrides E:\ base, never write E:\),
   **RUNS** on Cemu → packer/deploy/override are all correct; authored-raid's crash is our content.
5. **ROOT CAUSE (ghost-free, vs genuine): the XModel converter DROPS large inline-material images.**
   `skybox_mp_raid` emits **15,380 B vs genuine 1,588,228 B** — it drops its ~1.5 MB inline skybox
   texture. 36/440 raid XModels under-emit **3.68 MB** total. Skybox renders every frame during the
   load screen → dangling texture → GPU wild-pointer = raid's crash. **Almost certainly explains skate
   too** (skate has a skybox).

**Ruled out this session (clean measurement; do NOT re-chase):** images-broadly (standalone-Material
inline images emit fine), pointer-bake OOB (live materialHandles 0 OOB), StringTable/clipMap/GameWorldMp/
config (all match genuine), sound. **Methodology warning:** `LS.simulate` re-walk is unreliable for
per-asset sizes across policies (use assemble `out_assets` paired vs genuine); value-range pointer scans
are ~77% false positives (floats alias 0xA0–0xBF). Several static leads dissolved before the ground-truth
byte-diff pinned the skybox.

**UPDATE 2026-07-12 — A1 IMAGE FIX DONE + HARDWARE-VALIDATED; raid BOOTS + RENDERS.**
The XModel-inline image fix is complete: `RESIDENT_IMAGE_TEST` (ipak-membership discriminator)
built from base+mp.ipak in `produce_container`, so images in the streaming ipak STREAM (real
body, not the 1×1 stub) and only genuinely-resident images inline. Balloon fixed (215 MB → 95.3
MB; genuine 86 MB), GATE PASS, anchors PASS, unresolved 0, EOF-exact. On Cemu: mp_raid.ff loads,
streamed textures resolve from mounted base.ipak, renders frames. The load/null-texture risk is
GONE. New build deployed (prev preserved as `mp_raid.ff.prevbuild_bak`). Code: `material_convert.py`
(XMODEL_IMAGE_SOURCE + RESIDENT_IMAGE_TEST + convert_image branch), `xmodel_convert.py`,
`produce_container.py`. Detail: `HANDOFF_xmodel_inline_image.md`.

**CURRENT RAID BLOCKER = SndBank AX voice-callback crash (+0x3817ce, R13=0x1c8/R15=0x1d8), ~5 s
into rendering.** SEPARATE, pre-existing audio blocker — nothing the image fix touched. The
field-aware fix cleared it only in a bisect build that used the genuine english insert;
`author_english_bank` + checksum overlay are NOT yet wired into `produce_container`'s general
path. That's the next step for a clean raid boot (shared audio converter → benefits skate + ZM
too). Scope from the SndBank handoffs before coding.

**NEXT ACTION:** wire the SndBank general-path fix (author_english_bank / checksum overlay) into
`produce_container`, validate on raid (oracle) → clean raid boot → then carry image+sound fixes
to skate, then the ZM insert set for zm_transit/zm_nuked.

## SKATE BOOTS + ADVANCES — iterating on map-init (2026-07-11, ⚠ SUPERSEDED by LATEST above)
_The "misaligned-field / 0x0308001f" crash hypothesis here is DISPROVEN — see LATEST. Kept for the
calibration-loop method, which is still valid._

The artifact **loads, links, and runs into map-init on Cemu** (was crash-on-contact). Breakthrough:
a **full-memory crash dump IS the loader's ground-truth runtime layout**, so we MEASURE the
(un-derivable) console runtime band instead of deriving it, and bake pointers to match — a
self-bootstrapping calibration loop. 3 distinct bugs fixed this session, each advanced the boot
(runtime-map calibration; block-5 size; interp). Current crash = a garbage pointer-field read
(measured asset with a misaligned field / unrelocated ptr — a converter/layout bug, not the runtime
map). **Full iterate+debug loop, commands, paths, gotchas, next steps: `HANDOFF_skate_boot_iteration.md`**
(+ `FINDINGS_skate_boot_dump_calibration.md`, memory `skate-boot-1-result`).

## ARTIFACT #1 DELIVERED (2026-07-10, superseded by the boot-iteration state above)
`skate_artifact/`: `mp_skate_wiiu.ff` (33 MB, round-trips byte-exact) + `mp_skate.ipak`
(209 MB: 302 genuine-copy + 722 PC-streamed) + `mpl_skate.all.sabl/.sabs` + `BOOT_SHEET.md`.
Built by `native_linker/produce_container.py` (NEW: container author over the Track G
assemble). **Offline-verified:** skate authored zone re-walks **EOF-exact, 802 assets, 0
span gaps**, assemble **unresolved=0**; raid container dry-run **explained-clean** (strings
byte-equal, asset array 889/889 rows, hp aliases 3 structural + 2 ts-dangle + 0 bad, raid
re-walk EOF-exact 873); anchor suite PASS. **#1 registered boot risk = console GfxWorld
`gfx_skip` band unmodeled for skate** (our_policy=None stream-linear; genuine raid 749,115
/ dock 471,012 = GX2/DPVS runtime alloc, NOT count-derivable — 9-zone regression ±184K).
That is the headline of the first-boot-debug tier. See `HANDOFF` container doc + memory
`container-author`.

## Status in one line
**raid BOOTS + RENDERS on hardware; the image-drop bug is fixed; the only remaining raid blocker is
the separate, pre-existing SndBank audio-callback crash.** RE risk retired; converters oracle-validated;
pipeline builds/packs/deploys; the XModel-inline image fix (A1) is done and hardware-validated (raid
loads, streams textures, renders). Remaining is bounded and known: wire the SndBank general-path fix
(shared audio converter — helps skate + ZM), then carry image+sound to skate, then the ZM insert set.
_(The older "finish Track F / weeks-not-longer" framing below predates the boot attempts.)_

---

## The pipeline (stages)
```
PC .ff ──▶ [1 UNLINK] decrypt+decompress ──▶ PC zone
        ──▶ [2 WALK]   pc_walk dispatcher: locate every asset (end-of-zone)
        ──▶ [3 CONVERT] per-asset PC→console converters (+ techset substitution, + region generators)
        ──▶ [4 ASSEMBLE] emit full console zone from PC alone (whole-zone omap relocation)  ← Track G
        ──▶ [5 PACK]    console zone → Wii U v148 .ff
        ──▶ [6 IPAK]    author the map .ipak from PC image sources (base+mp+dlcN)
```
Orchestrator: `native_linker/pc_convert_pipeline.py` (also the GUI's "PC Fastfile → Wii U + IPAK"
page). Today it runs a raid-backbone splice; Track G replaces that with true no-backbone assembly.

---

## Component status

### ✅ DONE & VALIDATED
| Area | What | Evidence |
|---|---|---|
| **Fastfile I/O** | decrypt PC v147 / WiiU v148 / Xbox360 v146; pack WiiU v148; sig-bypass | boot-confirmed |
| **Geometry (vd0/vd1/indices/surfaces)** | group-aware vertex convert, swap2 vd1, stored `vertexDataOffset0`, no reorder, material-ptr reloc | **HW-confirmed on Cemu** (`mp_raid_GEOMDIAG3/4`) |
| **Material** | 104 B console converter | 437/446 byte-exact vs common_mp oracle |
| **XModel (rigid)** | body+bones+surfaces+materialHandles+collSurfs+boneInfo+physpreset | full driver 186/0 clean resync |
| **FX** | FxEffectDef header converter | 388/388 byte-exact |
| **Techsets** | genuine-console **substitution** (name grammar, not blob signature) | mp_skate **0 unresolved** (202 exact + 34 struct + 5 prefix) |
| **Images / ipak** | PC GfxImage enumerate → GX2-tile → author WiiU ipak; general | byte-exact vs retail (mp_la 287/287) |
| **DLC ipak sourcing** | maps stream from `dlcN.ipak`; auto-select wired | mp_skate skips 397→7 |
| **PC walk (traversal)** | dispatcher reaches **end-of-zone on mp_skate (840)** + raid; all complex types dispatched | 8+ raid-luck bugs fixed via OAT-load-order diff |
| **GfxWorld localization** | skyBoxModel XString + DPVS reads clean on all maps | 5 fixes, raid no-regress |
| **Track F asset-list ordering** | console order = PC order + type remap + mode-specific inserts | multi-map validated (raid+dockside+zm_transit ≥0.9975) |

### 🟡 IN PROGRESS
| Area | State | Doc |
|---|---|---|
| **Track F — no-backbone region generation** | ✅ **DONE 2026-07-10.** Every GfxWorld region emits: `native_linker/gfxworld_emit.py :: emit_gfxworld(pc, off, ctx)` → (bytes, fixups, log). Raid oracle-validated (body + all regions byte-exact mod registered classes), dockside spot-checked, **mp_skate GfxWorld emits end-to-end (22.89 MB: `skate_gfxworld_trackF.bin` + `_fixups.json`)**. smodelDrawInsts SOLVED (axis = 3× 10:10:10 rows, round(c*511) — 7698 insts exact across 2 maps, no stub). Lightmaps = RGBA8→BC3 512-block restack reencode; streamInfo = registered KD synthesis; cells/materialMemory/probe-cubes/outdoor/tail-lut = converters. **⚠ Assemble MUST inject Track B techsets into inline-material streams (CAVEATS §Integration) — the stream is not loadable without it.** | `CAVEATS_gfxworld_trackF.md` |

### ⬜ REMAINING (bounded, known-shape)
| Area | Gate for | Notes |
|---|---|---|
| **Track G — no-backbone assemble** | first boot | 2026-07-10: **CONTENT BAR DONE** — genuine raid walk is byte-exact to EOF (clipMap/SndBank/XAnimParts probe dispatches in `loader_sim`; the "clipMap gap" + 13 MB tail fully explained — the tail was the two SndBanks incl. the console-only localized `mpl_raid.english` insert). Chase converters integrated ≥2-map byte-exact: NEW `clipmap_convert.py`, `convert_gameworldmp`, `convert_scriptparsetree` (SPT 13/13 exact at gate). Gate: 127 exact + 737 allowlisted + 2 aliased-twin; ALL 9 remaining violations are POINTER-ONLY, root-caused + measured as the **runtime-allocation/interior-alignment model gap** (console +0.94 MB shift at raid tail, PC ~21 MB; interior drift ~360 B/12 MB) — see `HANDOFF_assemble_runtime_interior_model.md`. **2026-07-10 (later): that model is BUILT** — `alloc_events.py` event walkers + `loader_sim.replay_events` + solved constants baked in `raid_oracle_control` (console gfx_skip 919776, clipMap pre_skip 92, dynEnt lump 7816; PC gfx_skip −10,402,376 via the 516-anchor joint solve); gate resolution is stream-space; Omap gained GfxWorld rt-guard/opaque-techsets/string-resourcing/event-fine/scaled-verts0 regions. Gate now: 8 violations = DestructibleDef ×6 (222 geometry-share ptrs — PC content-dedup destroys semantics; needs the structural DD→XModel share map) + GWMP 1 + clipMap 1 (295 residual dedups into the PC pre-GfxWorld ~100 K drift band); hard=0 everywhere. skate blind assemble: 835/835, ALL unresolved attributable (GfxWorld 23,028 + techset-interior 347). CAVEAT: constants raid-only — genuine dockside walk desyncs pre-clipMap (old @758 break) and must be fixed for the 2-map bar. See `FINDINGS_runtime_interior_model.md`. **Track F emit INTEGRATED (same day):** GfxWorld row emits via gfxworld_emit (raid 21.8 MB, skate 22.6 MB — skate assemble ZERO missing rows, first full-coverage emit); INLINE_TECHSET_HOOK injects Track B blobs into FOLLOW-techset material streams; drawSurf verbatim fix landed (material oracle unchanged 437/446). Post-integration bar PARTIAL: unresolved=24.7K raid / 32.4K skate, ALL attributable but ~all are refs INTO the GfxWorld interior — needs the PC GfxWorld interior VIRTUAL model (which PC regions consume no virtual + per-region rt bases) before unresolved→0 / boot. **POLISH integrated:** lighting fix (vd0 tangent cross-lane rotate + vd1 per-group color-verbatim) live in the emit; SndBank loadedAssets = zeroed runtime buffer (raid bank 59.7→13.6 MB); author_english_bank ready (container wiring pending). New explicit caveat: SndBank head/aliases still LE byte-copy — BE field swap is an open converter item for sound. **2-MAP BAR CLOSED:** genuine dockside walks to EOF (gfxworld_console_span + G2 resyncs; dockside serializes planeCount−1 planes) and the dockside oracle gate runs (raid_oracle_control parametrized): GWMP 674/675, clipMap 221 residual, DD ×2 — mirrors raid. Constants per-zone via loader_sim.derive_gen_policy + gate delta-histogram closing (dockside 564,984/4,952/−492). PC gfx interior model still open (verifies to within 63,283; one alloc class missing; console runtime is MID-gfx +749,115 pre-planes). New caveats §14–16 (techset-hook blind path fires once on skate: hdr_create_lut2dv; dockside XAnim +6B defect; 2 corpus-gap techsets).) **Directive session 2:** DD share-map premise RETIRED (the 222 ptrs = DestructiblePiece string members whose GENUINE values dangle — stale linker heap; gate stale-str class → raid DD clean); XAnim +6 = source recompile (rule added, converter exonerated); DPVS-mirror arithmetic tested — does NOT close (OAT runtime family ≈338 KB vs console 919,776 → console-specific GX2 allocs). Gate: raid 2 violations / dockside 3 — ALL remaining = string dedups in the XModel/techset interior drift band ⇒ single remaining mechanism = XModel/FX/techset interior event model (also gates unresolved→0/boot). `raid_oracle_control.py dockside` = 2nd-map gate. **Part B session 2 (2026-07-10, ADDENDUM 9): PC gfx interior model LIVE (`pc_structural_gfx` split-flag + blind knobs A/B/E_mm, `loader_sim.derive_pc_policy`), region-paired fine map in Omap (blanket gfx tags GONE), CONSOLE gfx interior SOLVED (749,115 = pre-planes runtime band; `gfxworld_console_events` + `co_structural_gfx`, 2-map), conv_cells audit clean. unres:GfxWorld = 0 on ALL zones; unresolved raid 24,671→336 / dock →527 / skate 32,413→295, ALL = unres:techset-interior (decomposed: 144/168 = PC content-dedups into DXBC bytecode; needs per-field positive predicates — `HANDOFF_assemble_pc_gfx_interior_3.md`). raid gate PASS · dock 0-mod-typed · anchors PASS · skate blind fatal-bar green. GATE PASS not yet declared (unresolved ≠ 0).** **Main session 2026-07-10 (ADDENDUM 10): ✅ GATE PASS DECLARED — unresolved = 0 on raid AND skate.** The techset-interior class was decomposed per-field (diag_ts_*.py): real pointer fields (XModel materialHandles/texdefs/surf-hdrs/bone-arrays, FX/Material texdefs) dedup'd by the PC linker into DXBC bytes; content-lookup re-source proven IMPOSSIBLE (the content exists in neither our stream nor the genuine console zone — genuine ships these fields dangling and runs). Shipped as two typed classes: **ts-dangle** (in-bounds mirror into our substitute blob — boot-safe vs the old 0.5 GB poison; raid 336/dock 441/skate 276) + **ts-noise-verbatim** (clipMap/ComWorld/Glasses data words pass through, preserving genuine float content; dock 74+8+1, skate 19). Gate TECHNIQUE_SET×TECHNIQUE_SET unequal-content class replaces the (#tagged, ts-interior) allowlist, same coverage. Final: **raid gate PASS unresolved 0 · skate blind unresolved 0 (fatal bar green, blind constants) · dock unresolved 3 = 2 CAVEATS §16 missing-blob techset refs + 1 GfxWorld-pending · anchors PASS · all self-checks green.** ⇒ container-authoring GO; DLC session may proceed onto patch_zm. |
| **MAP_ENTS + duplicate-SOUND body** | first boot | CORRECTED (2-zone confirmed, raid+dockside): console insert = **ALIASED MAP_ENTS row @idx1 (raw type 48; raw 47 = GLASSES)** — no inline MAP_ENTS body to synthesize — plus one extra FOLLOW SOUND body: 2026-07-10 IDENTIFIED as the **localized bank `mpl_<map>.english`** (raid: 6,663 B; the main `mpl_<map>.all` is 12.97 MB incl. 11.5 MB inline loadedAssets). The `.english` bank must be authored for the boot artifact (small; alias metadata only). |
| **First build → Cemu → iterate** | first boot | first end-to-end run; expect first-boot debugging (omap/ordering) |
| **Lighting repack** (tangent + vd1-V) | correct render | ✅ SOLVED 2026-07-10 (`lighting_repack.py` + validator + `FINDINGS_lighting_repack.md`): darker-render = vd0 TANGENT cross-lane 1-bit rotate (lo>>1\|hi₁₅<<15, hi<<1\|lo₀ — 100.0000% byte-exact, 162,752 raid verts + dockside) + vd1 was NEVER flat swap2 (per-group stride 4/8/12/16: f16 lmap-UV swap2 + VERBATIM RGBA8 color words; 0 diff bytes both maps). Residual: 10/4.4M dockside subnormal-UV low bits (registered, invisible). **INTEGRATION OWED: assemble session applies the 3-line note** (conv_world_vertex36 + conv_vd1 drop-ins) |
| **Menu registration** (mapsTable / DLC gate) | playable/selectable | 2026-07-09: DLC load issue FULLY RESOLVED on Cemu (native `dlc0_load_mp.ff` loads — the earlier `Sys_Error` fork is closed). 2026-07-10: **PARKED — blocked on the linker**: new mapsTable rows require RELINKING `patch_zm`, i.e. the Track G assemble applied to a non-map zone. Resume on main-session thumbs-up (gate PASS + Track F landed = linker ready); patch_zm relink then doubles as the linker's second end-to-end proof. **2026-07-10: RELEASED EARLY** — the job is a console→console round-trip (event walkers + runtime constants + loader_sim, all 2-map proven), independent of the PC-conversion gate's last DXBC class. See `HANDOFF_dlc_patch_maptable.md` (stage gates: walk → byte-exact no-edit round-trip → row edit) |
| **Collision** | playable | ✅ RESOLVED (stale "109/465" retired 2026-07-10): XModel collmaps chain span-mismatch **0/459 skate, 0/437 raid** (`convert_xmodel_collmaps`, 2026-07-07) + world clipMap byte-exact HARD=0 raid+dockside (`clipmap_convert.py`). No collision work owed. |
| **Sound (SndBank)** | playable | ✅ PREMISE RETIRED 2026-07-10 (`FINDINGS_sndbank_loadedassets.md`): the genuine "11.5 MB inline audio blob" is ALL ZEROS on raid AND common_mp — a runtime-filled buffer (OAT: Alloc + runtimeAssetLoad); PC's same region = uninitialized linker heap. NO blob conversion exists; audio is FILE-level (`sab_convert.py`, already solved) from `content/sound/loaded/*.sabl`. mp_skate banks CONVERTED (`Converted_Sound_Banks/skate/`, .sabl 755 KB + .sabs 3.5 MB fmt-9). Zone authoring spec: entryCount = PC; dataSize = align2048(PC×0.21) (calibrated 0.1972/0.1948 both oracles). Registered opens (CAVEATS): genuine entryCount +2/+3 rule not reproduced (PC count self-consistent); SAB ids ≠ zone assetIds is GENUINE behavior — do not "fix". **INTEGRATION OWED: assemble emits zeroed buffer + authored dataSize fields; still owed: `mpl_<map>.english` bank authoring; deploy converted .sabl/.sabs beside the ipak** |

### 🧟 ZOMBIES TIER (separate, later)
| Area | Notes |
|---|---|
| **WEAPON consumer** | ✅ SPAN BAR DONE (2026-07-09): ALL zones walk end-to-end — raid 887, skate 840, nuketown 840, **zm_nuked 3158, zm_transit 3254**. No dedicated consumer needed: generic walker fixed (WEAPON/WEAPON_CAMO ASSET_ROOT, ptr2 double-ptrs, enum counts, partial reorder, asset_span inline-asset hook, menuDef_t union aliases, inline techset-in-material, clipmap rope-constraint materials). Remaining = CONVERT bar (PC→console weapon bodies vs zm oracle). See memory trackE-pc-walk-dispatcher |
| **Skinned skin-streams** | 3 Latte streams not PC-derivable; **run the OAT_NO_SKIN loader test first** — bind-pose-rigid may load and moot synthesis. `HANDOFF_skinned_skinstream.md` |
| **ZM asset-list inserts** | GLASSES/LEADERBOARD/LOCALIZE/XGLOBALS pattern (differs from MP) |

---

## Key technical findings (the "scary unknowns" that collapsed)
- **Geometry offset is a stored field.** `vertexDataOffset0` @12; no console reorder; the only bug was
  vd0's 16-byte group padding (needs group-aware convert). Overturned the entire original vd0 handoff.
  `FINDINGS_offline_RE_vd0_offset.md`.
- **Asset-list order is derivable**, not an unknowable reorder: PC order + type remap + mode-specific
  inserts (MP = MAP_ENTS + SOUND; ZM = GLASSES/LEADERBOARD/LOCALIZE/XGLOBALS). Multi-map validated.
- **Track F is ~90 KB of novel work**, not 11 MB — the rest is existing image-pipeline or
  surface-converter-shaped conversions.
- **Techset substitution keys on the name grammar**, not the blob signature (the 36→32 slot mirror
  makes blob signatures non-portable). 0 unresolved on mp_skate.
- **DLC = same offload model as stock**, just a different source ipak (`dlcN`/`dlczmN`).
- **SndBank alias METADATA serializes PC-identically, but the zone-level banks differ**: console
  carries `mpl_<map>.english` (localized insert) + `mpl_<map>.all`, and the inline loadedAssets data
  blob is platform-format (PC 59.7 MB vs console 11.5 MB on raid) — the old "byte-identical, plain
  byte-copy" claim was overbroad (2026-07-10 correction).
- **OAT never produced a bootable ff** — it's a per-struct byte oracle only (see the clarity tag in
  `HANDOFF_native_converters.md`); its "skin" work is the GfxWorld GPU shaders, not model skin-streams.

## Recurring methods & lessons (that made this fast)
- **OAT-load-order diff** — diff the probe/dispatcher against `*_t6_load_db.cpp` (the authoritative
  serialization order); finds the mis-sized/skipped field with no rebuild. Cracked GfxWorld
  localization + every downstream dispatcher bug.
- **Raid-luck-masking** — raid is repeatedly the degenerate/aligned case that hides bugs (asset-list
  align, GfxImage offsets, XAnim delta align, skyBoxModel alias, WEAPON absence, insert rules).
  **Always validate on ≥2 maps with console oracles before trusting a rule for a blind build.**
- **Matched-pair oracle** — convert PC body, diff byte-for-byte against genuine console (common_mp for
  MP shared assets; the map zone itself for ZM). "Byte-exact vs oracle = done."
- **Chase to root** — the visible drift is usually downstream of the real bug (destructible→PhysConstraints,
  XAnim→WEAPON, techset→2-byte upstream).
- **Stub-and-test** — for load-non-critical data (sound, MAP_ENTS, skinned), try a stub + loader test
  before investing in synthesis.

---

## Critical path to a first mp_skate boot
1. **Track F**: smodelDrawInsts converter → route 4 GX2-texture regions through ipak_stream (verify
   cubemap tiling!) → synthesize the ~90 KB console-only bits (validate sortedSurfIndex reorder vs oracle).
2. **MAP_ENTS + SOUND** bodies (cheap-synth or stub).
3. **Track G**: wire converters + generators + live omap into a no-backbone `convert_zone`.
4. **Assemble + pack mp_skate → first artifact → Cemu** (first-boot debugging milestone).
Then: lighting/menu/collision/sound polish for *playable*; WEAPON + skinned for the *zombies* tier.

## Parallelizable now (no critical-path collision)
- **Track F generators** (the frontier) · **WEAPON convert bar** (span done; zombies) · **DLC Step-0
  infra convert + Cemu menu test** · **geometry lighting repack** (polish).
- **Hold:** repo migration (breaks live sessions' paths); Track G (serial, needs F).

---

## Document & memory index
**State/index:** this file · `HANDOFF_native_converters.md` (converter tracks A–G overview) ·
`HANDOFF_main_session_state.md`.
**Per-area handoffs:** `HANDOFF_geometry_vd0.md` (0-SOLVED) · `HANDOFF_trackB_techset_substitution.md`
+ `_corpus_expand_and_fallback.md` · `HANDOFF_trackC_xmodel_surfaces.md` · `HANDOFF_trackE_pc_walk.md`
· `HANDOFF_trackF_nobackbone.md` · `HANDOFF_gfxworld_dpvs_sizing.md` · `HANDOFF_geometry_build2_culling.md`
· `HANDOFF_skinned_skinstream.md` · `HANDOFF_dlc_autoselect_wiring.md`.
**Findings:** `FINDINGS_offline_RE_vd0_offset.md` · `FINDINGS_gfxworld_localization_diag.md` ·
`FINDINGS_dlc_ipak_investigation.md` · `FINDINGS_loader_sim_pointer_model.md` ·
`FINDINGS_chase_content_gaps.md` · `HANDOFF_assemble_runtime_interior_model.md` (Track G active frontier).
**Memory:** `native-linker-handoff` (⭐ clean state) · `vd0-offset-re` · `trackA-material-converter` ·
`trackB-techset-translate` · `trackC-xmodel-converter` · `trackE-pc-walk-dispatcher` ·
`trackF-nobackbone-assemble` · `gfxworld-localization-drift` · `dlc-ipak-partition` ·
`wiiu-map-menu-registry` · `wiiu-sig-bypass` · `wiiu-sab-converter`.

## Constraints
- **Never write under `E:\`** (installed game) — copy `.ff` out before decrypt (ff_decrypt writes next
  to input). Reading E: is fine.
- struct_layout is WRONG for GfxWorld draw-onward and several console sizes (Material 104-not-112,
  XSurface 128-not-64, GfxImage offsets) — trust the probes + empirical pins, never struct_layout.
- Cemu runs the **installed** RPL (runtime = file + 0x2000).
