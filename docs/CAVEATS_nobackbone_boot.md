# CAVEATS — known limitations carried into the first no-backbone mp_skate boot

Honest register of every deliberate approximation / unresolved item in the no-backbone conversion, so
the first Cemu boot's outcome can be interpreted correctly (not chased as a mystery). Each entry:
**what it is · the bar it meets · does it need resolving · what adjudicates it.**

## Governing principle — the validation bar
**Genuine byte-parity is NOT the bar** (a no-backbone map has no genuine console counterpart to match).
The bar is **self-consistency = loadability**: re-walking our emitted bytes with the proven console-side
parser must consume **exactly** the emitted length. Every "✅ stream-valid" claim means that, not
byte-identical-to-genuine. Do not spend effort making outputs byte-match genuine; make them
self-consistent and loadable.

---

## 1. Skinned XModel surfaces → emit-rigid
- **What:** the 3 console-only Latte skin-streams are **not derivable from PC data** (confirmed
  independently by OAT). We emit affected surfaces **rigid** (no skin streams). mp_skate has **7**
  skinned XModels (measured; the earlier "0" was wrong).
- **Bar / correctness detail:** to be loadable, emit as a **genuine rigid** surface — **clear `flags&2`**
  and omit vertsBlend/streams, render the stored bind-pose verts. If the skinned flag is left set with
  streams absent, the loader may fault (expects stream data that isn't there). Flag-cleared rigid =
  stream-valid and load-safe.
- **Needs resolving?**
  - **Loading:** No — flag-cleared rigid is durable.
  - **Animation:** renders **frozen in bind pose** (no bone deformation).
    - Static/ambient skinned props (likely what mp_skate's 7 are — MP maps keep characters/weapons in
      common_mp) → visually fine, **permanent, no fix owed.**
    - Any actually-animated model → looks frozen; needs real Latte skin-stream synthesis (deferred).
      **Mandatory for the zombies tier** (zombie characters / wonder weapons); optional-cosmetic for MP.
- **Adjudicated by:** first boot (does flag-cleared rigid load?).
- **IMPLEMENTED + IDENTIFIED (2026-07-07):** `convert_surface_header(force_rigid=True)` — clears
  flags&2, consumes the PC vertsBlend/tension pre-verts0 blob (sizes per the proven xmodel_pc walk),
  leaves stream slots null. Result: **mp_skate 466/466, raid 440/440** emit + span-exact +
  console-rewalk self-consistent. The 7 mp_skate skinned models (assets 634–642 + 648):
  `fxanim_mp_skate_ferris_wheel_mod`, `fxanim_gp_teardrop_flag_blue_mod`, 4 alias-named siblings in
  the same fxanim block, and `german_shepherd` (dog scorestreak). All ambient/fx-anim props or the
  dog — **none load-critical; emit-rigid is PERMANENT for mp_skate MP** (frozen ferris wheel / limp
  flag = cosmetic; frozen dog only if the scorestreak fires). Real synthesis stays zombies-tier.
- **Tracked:** `HANDOFF_skinned_skinstream.md` (real synthesis = zombies tier).

## 2. −16 / −32 genuine-size class (XModel bodies)
- **What:** a subset of XModel bodies emit 16 or 32 bytes different in size vs the genuine console body;
  **not root-caused.**
- **Bar:** **self-consistent** — re-walks to exactly the emitted length, so stream-valid/loadable.
- **Needs resolving?** No, by the loadability bar. Harmless unless the first boot proves otherwise.
- **Adjudicated by:** first boot. If a specific model faults, root-cause *that* one then.

## 3. Streamed-image → console-inline fallback (inline-material GfxImages)
- **What:** PC-streamed inline images (`resourceSize=0`) emit a console **streaming** body; the pixels
  resolve from the **map `.ipak`** (which the pipeline builds from PC sources).
- **Bar:** stream-valid body; correct render **depends on ipak coverage** of the referenced images.
- **Needs resolving?** Only if coverage is incomplete. mp_skate's ipak = base+mp+dlc1 with **7
  engine-builtin skips** (`$identitynormalmap`, `$outdoor`) → coverage is good, risk low.
- **Adjudicated by:** first boot — a missing image shows as a visible gap or a load error.

## 4. Lossy bonedata / vertex floats
- **What:** low-bit differences in bone bounds/quats (console re-derives from its re-quantized mesh) and
  normal/tangent (PC's 10-bit encoding already lost precision).
- **Bar:** inherent, not a bug. Sub-perceptual.
- **Needs resolving?** No.

## 5. memUsage@204 (XModel)
- **What:** a console-**computed** memory stat, not PC-derivable; emitted best-effort.
- **Bar:** a stat field, non-fatal.
- **Needs resolving?** No (unless a loader path is found to read it strictly — unlikely).

## 6. Material 437/446 (hashIndex)
- **What:** 9 model materials differ by 2 bytes @off 34 (a sort hash); low-impact.
- **Bar:** loadable; the sort hash is cosmetic.
- **Needs resolving?** No for boot; a later polish item if sort order ever matters visibly.

## 7. Geometry lighting (tangent + vd1 second-UV)
- **What:** tangent and vd1's second u16 (lightmap V) are console-repacked, not byte-swappable → the
  map renders **slightly darker / less vibrant.**
- **Bar:** geometry is correct; lighting is cosmetically off.
- **Needs resolving?** Deferred polish (bounded RE — reverse the packing). Not a boot blocker.
- **Tracked:** `FINDINGS_offline_RE_vd0_offset.md`.

## 8. WEAPON (not applicable to mp_skate, general caveat)
- **What:** no WEAPON PC consumer yet. mp_skate has **0 inline weapons**, so N/A here. Blocks nuketown
  (MP, 1) + all ZM maps (~100/zm).
- **Adjudicated / tracked:** `HANDOFF_weapon_consumer.md` (zombies-tier + nuketown).

## 8b. Pointer values: runtime-allocation + interior-alignment model gap (BOOT BLOCKER until modeled)
- **What:** alias pointer VALUES encode the loader's runtime cursor. Two effects are currently
  unmodeled in `loader_sim` (2026-07-10 measurements, raid oracle): (1) **RUNTIME-block allocations**
  (GfxWorld's runtime regions ≈ +0.94 MB on console raid, ~21 MB on PC; GWMP basenodes; possibly
  clipMap dynEnt lists) shift every later allocation; (2) **per-allocation alignment inside
  delimiter-walked (verbatim) assets** drifts interior targets by up to ~hundreds of bytes (SndBank
  anchors: 940,400..940,760 across one 12 MB bank). Consequence: alias values our assemble emits for
  targets inside/after clipMap, GWMP, SndBank (and post-GfxWorld generally) are wrong by these deltas
  and would mislead `ConvertOffsetToPointer` at load.
- **Bar:** NOT yet met — this is the one remaining gate item. The structural bytes (hard-diff) are
  clean; only pointer values in these regions are affected.
- **Needs resolving?** YES before the first boot artifact.
- **Tracked:** `HANDOFF_assemble_runtime_interior_model.md` (event-walker plan + oracle anchors).

## 9. Runtime tooling caveat — Cemu errors are opaque (IMPORTANT for debugging the first boot)
- **What:** Cemu does **not capture `OSReport`** for this retail build (0 lines even with coreinit
  logging), so a `Sys_Error` **message string is invisible.** The DLC-infra session hit a `Sys_Error`
  on the `DB_Thread` (fastfile loader) visible only as a symbolized **stack**
  (`FatalThreadFunc ← Sys_Error ← DB_Thread`).
- **Implication:** the first mp_skate artifact, if it fails, will likely give a **stack but no reason.**
  So: (a) offline self-consistency + the omap fatal-assert + container round-trip are your primary
  signal — invest there; (b) symbolize any crashlog with `wiiu_ref/rpl_symbolize.py`; (c) don't expect
  a readable error message. NOTE the DLC crash was in the *load-zone* path (thin `_load_` frontend
  zones), a **different asset** than the map `.ff` — it doesn't predict a map failure, but the
  invisible-error tooling gap applies to any boot.

---

## How to read the first boot against this list
- **Loads & renders (maybe dark, maybe a frozen prop or two):** expected best case — the caveats above
  are all "acceptable" by design; log which manifested.
- **Loads, missing a texture:** caveat #3 (ipak coverage) — add the pack/image.
- **Sys_Error on DB_Thread, no message:** symbolize the stack (#9); suspect an un-self-consistent body
  (#2 first suspect) or a load-required stubbed region — the offline asserts should have caught most.
- **A specific skinned model faults:** caveat #1 — verify the flag was cleared (rigid), not left skinned.

## POLISH session additions (2026-07-10)

## 8c. SndBank loadedAssets — premise CORRECTED (supersedes §8b's "platform-format audio blob")
- **What:** the in-zone loadedAssets entries+data are a **zero-filled runtime buffer** on genuine
  console (2-map verified: raid 654×20 B + 11,519,896 B zeros; common_mp 810×20 B + 23,951,128 B
  zeros). No blob conversion exists. Audio is converted at FILE level (.sabl/.sabs via sab_convert;
  mp_skate banks already converted → `Converted_Sound_Banks/skate/`). Zone authoring: entryCount =
  PC verbatim; dataSize = align2048(PC × 0.21) (genuine ratio 0.195–0.197); bytes = zeros.
  See FINDINGS_sndbank_loadedassets.md.
- **Registered residuals:** genuine console entryCount is +2/+3 above PC (rule not reproduced;
  capacity-safe with PC count since we ship PC aliases); SAB entry ids ≠ zone assetIds on BOTH
  platforms (genuine works that way — do not "fix" ids).

## 12. GfxWorld vd0 UV denormal class (lossy, cosmetically nil)
- **What:** a handful of degenerate world vertices store f32 SUBNORMAL UVs whose low bits differ
  console-vs-PC (linker denormal flush). mp_dockside: 10 of 4.4M verts, UV field only; raid: 0.
  Not derivable from PC at bit level; invisible at render. lighting_repack_validate.py reports it.

## 13. vd1 column classifier is a calibrated vote (not a struct-derived truth)
- **What:** vd1 element layouts (UV layers vs trailing RGBA8 color words) are classified per column
  by an f16-plausibility majority vote (exponent window [5,17]), byte-exact on raid+dockside
  (0 diff bytes). A future map could in principle defeat the vote (symptom: a wrongly tinted
  surface, not a crash). `lighting_repack.conv_vd1` accepts `col_override` for manual pinning.

## 14. INLINE_TECHSET_HOOK is a NAMED BLIND PATH at boot #1
- **What:** materials whose techniqueSet ptr is FOLLOW/INSERT get a Track B substitute console
  techset blob emitted IN PLACE (`material_convert.INLINE_TECHSET_HOOK`, installed by the
  assemble). No oracle exercises it: all 352 genuine raid materialMemory inline materials ALIAS
  their techsets (slot refs; region re-parses end-exact with zero inline techsets).
- **mp_skate exposure (measured):** the hook fires for exactly ONE techset —
  `hdr_create_lut2dv_827z0f8q` (the tail lut material). If boot #1 dies in/near the GfxWorld
  tail material, suspect this injection first (blob shape/placement unverified vs any genuine).

## 15. XAnimParts converter defect on dockside (1 asset)
- **What:** the dockside oracle gate pairs one XAnimParts at 16,047 emitted vs 16,053 genuine
  (+6 bytes, then wholesale hard-diff from offset 3,412) — a convert_xanim walk/size gap not
  present on raid (raid XAnims are exact). Un-diagnosed; registered, not shipped-around.

## 16. Two dockside techsets have NO corpus blob (MISSING at the dockside gate)
- **What:** `techset-subst: no blob for asset @0x89e00da / @0x89e1b64` — dockside PC techsets
  that neither exact-name nor struct-fallback resolve. Dockside is a validation zone (not a
  ship target); if a ship-target map hits this class the corpus needs those blobs.
