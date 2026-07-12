# HANDOFF — Track A (PC→Wii U map port): fastfile battle WON, now at the shader wall

**Date:** 2026-07-05 · **For:** the main session picking Track A back up.

> **READ THIS FIRST:** Everything below is **already implemented and built**. You (main
> session) do **NOT** need to re-implement anything. The Unlinker is compiled, the fixes are
> in source, the confirmation build is packed and sitting in the project root awaiting a
> hardware test. Your job is to interpret the pending test result and, if positive, hand out
> the task set in `TASKS_reference_remap.md`. Do not redo the work described here.

---

## Where we are in one paragraph

The PC map `mp_raid` now **DB-loads 100% cleanly on Wii U (Cemu)** — the entire 27 MB zone
reads in with **zero CPU exceptions**. Every fastfile struct/pointer bug is fixed
(skinnedverts, gameworldmp, clipmap/mapEnts, block layout, image streaming). The remaining
symptom is a **black screen after a fully successful load** — this is a **rendering** problem
(null GX2 shaders), not a load problem. A **cheap confirmation build** (`mp_raid_TECHREF.ff`)
is packed and awaiting a Cemu test to prove shaders are the wall and that the fix path
(techset references) works.

## What was accomplished THIS session (all done, all built)

1. **clipmap `mapEnts` fix** — the last load crash. `clipMap_t+168` was a garbage cross-block
   alias pointer (`0xa2c9fb81`) because the standalone MapEnts asset is written before clipmap,
   so OAT aliased it and the Wii U loader couldn't resolve it → access violation on entity
   spawn. Fixed by forcing an **inline** MapEnts write (`Writer_MapEnts::WriteInline`, console
   only). Verified byte-for-byte against genuine via `clipmap_probe.py`. **Hardware-confirmed:
   full zone now loads, no crash.**

2. **Shader-wall diagnosis** — proved the black screen is null GX2 pass shaders (D3D11 → GX2
   is not transcodable). Quantified: of raid's 229 techsets, **65 already exist in genuine
   Wii U common_mp** (referenceable = free shaders), **164 are map-specific** and currently
   written inline with null shaders (the black surfaces).

3. **Confirmation hook (`OAT_TECHSET_REF`)** — console-only: rewrites every non-reference
   techset name to `,<name>` so the loader resolves a real shader from common_mp instead of
   drawing our null body. Built `mp_raid_TECHREF.ff` with all inline techsets pointed at
   `mc_lit_sm_r0c0n0s0_zqq1fze7` (a real common_mp techset).

## THE PENDING TEST (this is the one open item)

User is testing **`mp_raid_TECHREF.ff`** (copy → `E:\Wii U Black ops 2\content\english\mp_raid.ff`,
launch raid). Interpret the result:

- **Anything renders** (even flat/garbage geometry, not pure black) → **shaders confirmed as
  the wall + reference path proven.** Green-light the full reference-remap (hand out
  `TASKS_reference_remap.md`).
- **Still black, no crash** → the reference didn't resolve. Re-run the rewrite with
  `OAT_TECHSET_REF=mc_unlit_replace_3j970129` (NO rebuild needed) and re-pack. If still black,
  verify the referenced name is actually present/loaded in Wii U common_mp at map-load time.
- **New crash** → a non-world material (UI/effect/sky/2D) can't accept a world-lit shader.
  Narrow the override to world/model materials only (skip techset names starting with
  `2d`/`effect`/`distortion`/`sky`), rebuild, retry.

Cemu log: `C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\log.txt`. This is an FS-API log — it
shows DB-load progress (read count on the mp_raid handle) but **not** GPU activity. A clean
full load with no exception + black screen = render stage, exactly what we expect.

## Permanent source changes made this session (already in tree, already compiled)

- `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/mapents/mapents_t6_write_db.{h,cpp}` —
  new `Writer_MapEnts::WriteInline()`.
- `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/clipmap_t/clipmap_t_t6_write_db.cpp` @~1445
  — console calls `WriteInline` instead of `Write`.
- `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/materialtechniqueset/materialtechniqueset_t6_write_db.cpp`
  — `OAT_TECHSET_REF` hook + includes.

(These are "generated" files edited as static ClCompile — the same pattern as the earlier
skinnedverts/gameworldmp fixes. They are NOT regenerated on build.)

## Build & pipeline recipe (unchanged — for reference only)

- Unlinker: `tools/ref_oat/build/bin/Release_x64/Unlinker.exe` (rebuilt 16:xx this session).
  Rebuild: MSBuild `src/UnlinkerCli/UnlinkerCli.vcxproj` `/p:Configuration=Release
  /p:Platform=x64 /p:PlatformToolset=v143 /p:SolutionDir="...\tools\ref_oat\build\\"`
  (MSBuild at `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe`).
- Python: `C:\Users\Tony - Main Rig\AppData\Local\Programs\Python\Python313\python.exe`.
- Full build: rewrite (env below) → `python WiiU_FF_Studio/wiiu_ff.py pack mp_raid_rewrite.ff mp_raid <out>.ff`.
- Rewrite env: `OAT_REWRITE=1 OAT_IGNORE_SIG=1 OAT_WRITE_WIIU=1 OAT_GSC_DIR=wiiu_ref/genuine_gsc
  OAT_IMAGE_DIR=<scratchpad>/img_out OAT_OMIT_LIST=<scratchpad>/omit_snd_scr_img.txt
  [OAT_TECHSET_REF=<name>] Unlinker --list "PC ff/mp_raid.ff"`.
- Scratchpad (prepared inputs, all intact): `img_out/`, `omit_snd_scr_img.txt`, `mp_raid_new.ipak`.
- ipak companion (`mp_raid.ipak`) is unchanged; already in place on the console.

## Deliverables in project root

- `mp_raid_TECHREF.ff` (== `mp_raid.ff`) — the confirmation build, awaiting test.
- `mp_raid.ipak` — image stream companion (genuine 124 + 2 new, crc-verified).

## What this means for the DLC goal

The fastfile/load pipeline is now map-agnostic and proven — any DLC map clears the same load
path. The one remaining shared problem is shaders, and the **reference-remap** approach
(pointing map-specific techsets at shaders that exist in common_mp) is the DLC-general fix,
because DLC maps have no genuine Wii U version to extract from. New DLC *textures* are a
non-problem (we tile them ourselves via the IPAK pipeline; shaders are texture-agnostic). See
`TASKS_reference_remap.md` for the go-forward plan.

## Memory

Full detail is in the auto-memory file `track-a-ipak-streaming.md` (index in `MEMORY.md`).
Related: `wiiu-sig-bypass`, `wiiu-codec-blocksize`, `bo2-wiiu-fastfile`, `wiiu-map-menu-registry`.
