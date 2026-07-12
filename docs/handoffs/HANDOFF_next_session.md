# HANDOFF — Next session (BO2 T6 PC→Wii U port): the GfxWorld render wall

Self-contained. A cold session can run this. Read this first, then the referenced docs as needed.

## Where the project is (one paragraph)
Reverse-engineering Black Ops II (T6) Wii U fastfiles to port PC/DLC maps to Wii U. The ENTIRE load
pipeline is hardware-confirmed EXCEPT rendering the world: signature bypass (patched update-partition RPLs,
installed & confirmed), codec, textures/IPAK, techsets (real GX2 shaders), GameWorldMp, MapEnts, GSC,
streamInfo — all working. The ONE remaining wall is **GfxWorld**: our PC-derived GfxWorld is ~7.24 MB
smaller than genuine because it lacks console-only inline "gump" data (reflection-probe cubemap + lightmap
pixels stored in-zone, + post-vertex lighting tables). The Wii U loader walks/frees those gumps
(`DB_GumpShouldFree`) → missing → heap overrun → crash after a full clean DB-load. This is a content gap,
not a writer bug. Root cause + evidence: `DPVS_WALK_FINDINGS.md`.

## DO NOT REDO (solved & in the tree / installed)
RSA signature bypass; 0x7FC0 codec; all fastfile struct/pointer/block load crashes; PC→IPAK texture
streaming; sound-bank convert; GSC transcode; real GX2 techset shaders; GameWorldMp & MapEnts (were writer
bugs, fixed via genuine-inline hooks). The Unlinker is built with all hooks. Work on a COPY of
`tools/ref_oat` only if you rebuild it.

## The two goals & their paths
1. **Render Raid (retail, has a genuine Wii U version):** INLINE genuine GfxWorld. Infra is BUILT
   (`OAT_GFXWORLD_FILE` hook + `wiiu_ref/gfxworld_raid.blob`). REMAINING = write `wiiu_ref/gfxworld_remap.py`
   to rewrite the blob's internal asset-ref aliases to OUR zone's same-named assets. Full plan:
   `HANDOFF_gfxworld_inline.md`. Blocker: locating the ref fields (materialMemory[352]→Material, image refs)
   needs the GfxWorld MIDDLE mapped (the ~11 MB gump/lighting/dpvs region). Two ways to unblock:
   (a) finish the full GfxWorld structural walker (`HANDOFF_dpvs_walker.md` + `wiiu_ref/dpvs_walk_full.py`),
   (b) OR add a ContentWriterT6 write-time log of `assetName -> virtualOffset` for Material/GfxImage/XModel
   (the WRITE side knows both) to build OUR name→offset map cheaply, plus a genuine offset→name map.
2. **DLC (no genuine Wii U GfxWorld):** SYNTHESIZE the missing console content — 3 RE work items in
   `DPVS_WALK_FINDINGS.md`: (1) console GfxImage inline-pixel (gump) encoding after each probe/lightmap
   image body, (2) post-vd0 lighting tables (~4 MB), (3) true dpvs static array layout (lives ~0x3bd0000+,
   NOT the old 0x3536c79 anchor). This is the DLC-enabling capability; inlining Raid first captures the
   ground-truth format to synthesize.

## Recommended next step
Unblock the inline: pick unblock-method (b) above (write-time asset offset log — smallest, deterministic),
build both name/offset maps, then `gfxworld_remap.py`, then test:
```
OLD=<scratch>/scratchpad   # img_out + omit_snd_scr_img.txt (session 798d568c scratchpad)
OAT_REWRITE=1 OAT_IGNORE_SIG=1 OAT_WRITE_WIIU=1 OAT_DROP_GSC=1 \
  OAT_GFXWORLD_FILE=wiiu_ref/gfxworld_raid_remapped.blob \
  OAT_GAMEWORLDMP_FILE=wiiu_ref/gameworldmp_raid.blob \
  OAT_MAPENTS_FILE=wiiu_ref/mapents_raid.blob \
  OAT_TECHSET_DIR=wiiu_ref/techsets_raid \
  OAT_IMAGE_DIR=$OLD/img_out OAT_OMIT_LIST=$OLD/omit_snd_scr_img.txt \
  tools/ref_oat/build/bin/Release_x64/Unlinker.exe --list "PC ff/mp_raid.ff"
python WiiU_FF_Studio/wiiu_ff.py pack mp_raid_rewrite.ff mp_raid mp_raid_GFXINLINE.ff
cp mp_raid_GFXINLINE.ff mp_raid.ff   # user installs to E:\Wii U Black ops 2\content\english\mp_raid.ff
```
DONE WHEN: geometry renders on Wii U (first rendered map) — and the genuine gump format is captured for DLC.

## Paths / environment
- Unlinker: `tools/ref_oat/build/bin/Release_x64/Unlinker.exe` (built, all hooks). Rebuild (only if you edit
  writers): MSBuild `build/src/UnlinkerCli/UnlinkerCli.vcxproj /p:Configuration=Release /p:Platform=x64
  /p:PlatformToolset=v143 "/p:SolutionDir=<abs>/tools/ref_oat/build"` (VS2022 BuildTools).
- Python (has capstone): `C:/Users/Tony - Main Rig/AppData/Local/Programs/Python/Python313/python.exe`
- Genuine zone: `wiiu_ref/mp_raid_genuine.zone`; GfxWorld body @0x2b7029d, end @0x40aa61d.
- Our converted zone: `mp_raid_rewrite.ff` (regenerate with the env above, minus OAT_GFXWORLD_FILE, to get
  the PC-derived GfxWorld @0x3fcdd15). Test slot: `E:\Wii U Black ops 2\content\english\mp_raid.ff`.
- Cemu log: `C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\log.txt`. On a crash Cemu writes an inline
  crashlog AND a `AppData\Roaming\Cemu\crashdump\*.dmp`. **Grab the log immediately — a relaunch resets it.**
  Symbolicate: `python wiiu_ref/rpl_symbolize.py --threads` (names the last crashlog's guest threads). The
  crashing thread has a corrupted TCB (garbage name/IP); `Main IP 0x02240758` = DDL_LUI menu = red herring.
- ⛔ Never edit files under `E:\Wii U Black ops 2\...` or `E:\Call of Duty Black Ops II\...` — copy out first.

## This session's env-hooks (all in the built Unlinker; console-only, all env-gated)
| env | effect |
|---|---|
| `OAT_GAMEWORLDMP_FILE=<blob>` | write genuine GameWorldMp verbatim (blob=`gameworldmp_raid.blob`) |
| `OAT_MAPENTS_FILE=<blob>` | write genuine MapEnts verbatim (`mapents_raid.blob`) |
| `OAT_TECHSET_DIR=<dir>` | per-techset: if `<dir>/<name>.techset` exists, write real GX2 shaders (`techsets_raid/`) |
| `OAT_GFXWORLD_STREAMINFO=<blob>` | inject genuine GfxWorld streamInfo (`gfxworld_streaminfo_raid.blob`) |
| `OAT_GFXWORLD_FILE=<blob>` | write genuine GfxWorld verbatim — blob MUST be alias-REMAPPED first |
| `OAT_DROP_TYPES=<ids>` | omit assets by PC type id (e.g. 17=GFXWORLD,15=GAMEWORLD_MP,11/12=CLIPMAP) — bisection |
| `OAT_DROP_GSC` | omit scriptparsetree assets |

## Docs
`DPVS_WALK_FINDINGS.md` (crash root cause), `HANDOFF_gfxworld_inline.md` (inline+remap plan),
`HANDOFF_dpvs_walker.md` (full walker), `WIIU_UNLINK_STATUS.md` (master, top has the 2026-07-05 status).
Memory: `track-a-ipak-streaming` (2026-07-05 night1-17 = the full session log), `wiiu-native-unlinker`,
`wiiu-sig-bypass`, `wiiu-map-menu-registry`.
