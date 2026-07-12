# HANDOFF v2 — Track A (PC→Wii U map port): at the shader wall, SELFREF done → Branch B committed

**Supersedes `HANDOFF_trackA_shaders.md`.** Date: 2026-07-05 evening. For the main session.

> **SELFREF RESULT IN (2026-07-05 20:28): CRASH → Branch B.** Same-name reference stubs crashed
> identically to the single-target builds (host 0x7ff6acc617ce, regs R13=0x1c8/R15=0x1d8, Main IP
> 0x02240758) after a clean 105-read load. Since same-name is argument-safe, this proves the
> **rename-to-`,name`-stub reference method does NOT resolve on Wii U** — the loader doesn't swap it,
> so the zeroed-technique techset is dereferenced empty. **Committed direction: Branch B (inline real
> extracted GX2 shaders).** The "DECISION" section below is kept for the record; act on Branch B.

> **The work is already implemented and built.** Do NOT re-implement. Unlinker is compiled; all
> fixes are in source; the current test build is `mp_raid.ff` (== `mp_raid_SELFREF.ff`). Your job:
> (1) read the SELFREF test result the user reports, (2) branch per "DECISION" below, (3) hand the
> matching task block to a new session. Fill-in only — everything up to this point is done.

---

## One-paragraph status
`mp_raid` DB-loads 100% clean on Wii U (all fastfile struct/pointer bugs fixed & hardware-
confirmed: skinnedverts, gameworldmp, clipmap/mapEnts, block layout, image streaming). Remaining
symptom is a **post-load black screen = null GX2 shaders** (D3D11 shaders can't transcode to GX2;
our writer emits null pass shaders). We are proving out the fix path (name-based techset
references resolved from common_mp). A disambiguation build (`mp_raid_SELFREF.ff`) is under test to
decide whether Wii U resolves techset references at all.

## The shader mechanism (established)
Material → MaterialTechniqueSet → ~34 techniques → passes → {GX2 vertex/pixel shader}. A techset
whose **name starts with `,`** is a *reference*: the loader `DB_FindXAssetHeader(name+1)`-swaps it
from an already-loaded zone (common_mp). Genuine reference form = 136-byte body with the 32
technique-pointer slots **zeroed** and NO technique tree. Of raid's 229 techsets, **65 exist by
name in genuine Wii U common_mp**, **164 are map-specific** (only in genuine Wii U mp_raid.ff).

**Key constraint (learned this session):** a material's `MaterialShaderArgument` array is sized to
its ORIGINAL techset. Substituting a *different* techset breaks the arg contract → crash. So only
**same-name** substitution is argument-safe.

## Confirmation timeline (all hardware-tested)
1. CLIPFIX (no techset override): full load, **no exception, silent black hang**.
2. TECHREF v1 (rename only, full body kept): silent hang → renaming without stubbing didn't trigger
   the ref swap. Fixed the hook to emit the proper **stub** (zero technique slots, skip tree).
3. TECHREF2 (stub, ALL→one UNLIT target): full load (105 reads, no desync), **crash** 0xc0000005 at
   host `0x7ff6acc617ce`, guest Main IP `0x02240758`.
4. TECHREF3_lit (stub, ALL→one LIT target): **crash identical** — same host fault, identical regs
   (R13=0x1c8, R15=0x1d8). Single global target crashes regardless of lit/unlit.
5. **SELFREF (stub, only the 65 present techsets → SAME-NAME refs; 164 stay inline-null): UNDER
   TEST.** Same-name = argument-safe, so this isolates "do references resolve on Wii U at all?"

## DECISION — branch on the SELFREF result the user reports

### If SELFREF renders geometry OR silent-hangs (no crash)
→ **References RESOLVE on Wii U.** The single-target crashes were arg mismatches. Path = same-name
references for the 65 + real shaders for the 164. Give the new session **TASK BLOCK A** in
`TASKS_reference_remap.md` (note the arg-safety reframe there). Quick next probe: an all-65 render
means try adding channel-matched refs for a few of the 164 and watch for the first arg-crash.

### If SELFREF CRASHES (crashlog / 0xc0000005)
→ **References DON'T resolve on Wii U** (the loader isn't swapping; our zeroed technique slots then
deref). The reference approach is a dead end. Path = **inline real extracted GX2 shaders** from a
genuine Wii U zone. Give the new session **TASK BLOCK B** in `TASKS_reference_remap.md`. This
requires finishing the genuine-zone VIRTUAL-block walker (`techset_extract.py`, currently 5/229 +
55 refs; fails on block-5 alias resolution) — the hard tooling deferred this session.

(If it crashes, also grab the read count — 105 = clean load, crash is post-load as expected; a
lower count would mean the stubs desynced the stream instead, a different bug.)

## Source changes made (in tree, compiled — do not redo)
- `.../mapents/mapents_t6_write_db.{h,cpp}`: `Writer_MapEnts::WriteInline` (clipmap mapEnts fix).
- `.../clipmap_t/clipmap_t_t6_write_db.cpp` @~1445: console uses `WriteInline`.
- `.../materialtechniqueset/materialtechniqueset_t6_write_db.cpp`: techset hooks
  `OAT_TECHSET_REF=<name>` (single global stub target) and `OAT_TECHSET_SELFREF=<file>` (same-name
  stubs for listed techsets). Both console-only, both emit the proper stub form.

## Build recipe (unchanged)
- Unlinker: `tools/ref_oat/build/bin/Release_x64/Unlinker.exe`. Rebuild via MSBuild
  `src/UnlinkerCli/UnlinkerCli.vcxproj /p:Configuration=Release /p:Platform=x64
  /p:PlatformToolset=v143 /p:SolutionDir="...\tools\ref_oat\build\\"` (MSBuild under
  `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\...`).
- Python: `C:\Users\Tony - Main Rig\AppData\Local\Programs\Python\Python313\python.exe`.
- Rewrite env: `OAT_REWRITE=1 OAT_IGNORE_SIG=1 OAT_WRITE_WIIU=1 OAT_GSC_DIR=wiiu_ref/genuine_gsc
  OAT_IMAGE_DIR=<scratchpad>/img_out OAT_OMIT_LIST=<scratchpad>/omit_snd_scr_img.txt
  [OAT_TECHSET_REF=<name> | OAT_TECHSET_SELFREF=<file>] Unlinker --list "PC ff/mp_raid.ff"`.
- Pack: `python WiiU_FF_Studio/wiiu_ff.py pack mp_raid_rewrite.ff mp_raid <out>.ff`
  (NOTE: copy `<out>.ff` → `mp_raid.ff`; the pack's output-name arg is unreliable, so also
  `cp <out>.ff mp_raid.ff`). User copies `mp_raid.ff` → `E:\Wii U Black ops 2\content\english\mp_raid.ff`.
- Cemu log: `C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\log.txt` (FS-API only — shows load
  progress via read count on the mp_raid handle `3080289`; 105 reads = full load; does NOT show GPU).
- Inputs (intact): `present65.txt` (project root), scratchpad `img_out/`, `omit_snd_scr_img.txt`,
  `mp_raid_new.ipak`. ipak companion `mp_raid.ipak` unchanged, already on console.

## DLC relevance
Fastfile/load pipeline is map-agnostic and proven. For DLC (no genuine Wii U version): the 65
common techsets are referenceable; the map-specific remainder needs either arg-safe same-name
resolution (if the DLC map's techsets happen to exist in common) or extraction/arg-fixup. New DLC
textures are a non-problem (we tile them via IPAK; shaders are texture-agnostic). Menu/registry
gating: memory `wiiu-map-menu-registry` (mapsTable.csv, DLC gate @0x0241CBA0).

## Memory
`track-a-ipak-streaming.md` (index in `MEMORY.md`) has the full detail incl. this session's
confirmation timeline, the arg-safety insight, and both decision branches.
