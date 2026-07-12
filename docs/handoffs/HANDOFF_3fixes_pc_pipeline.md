# HANDOFF: 3 fixes to finish the PC → Wii U map/DLC pipeline

Context: The RSA signature wall is DOWN (patched update RPLs in Cemu mlc + hardware
plan exists). Zeroed-sig repacks fully load. Codec framing is fixed (0x7FC0 blocks).
Remaining blockers are all **content-correctness in the OAT write path**. Two live
test cases exposed them:
- **PC retail Raid** (well-formed retail map) → `Sys_Error("Out of memory")` at DB-load.
- **Custom dust2** → silent hard fault ~17 ms into DB-load (before textures).

Goal: make well-formed PC maps (retail + **PC DLC**, which the user has) load, then
custom maps. PC DLC uses this exact pipeline, so Fix 1 is the DLC unblock.

Key paths:
- OAT unlinker (x64): `...\Testing enviroment\tools\ref_oat\build\bin\Release_x64\Unlinker.exe`
- OAT source: `...\Testing enviroment\tools\ref_oat\src\`  (write path: `ZoneWriting\Game\T6\ContentWriterT6.cpp` + `ConsoleWriterT6.cpp`)
- Codec/pack: `...\Testing enviroment\WiiU_FF_Studio\wiiu_ff.py` (pack name must be `mp_raid` for the raid slot)
- Python w/ packages: `C:\Users\Tony - Main Rig\AppData\Local\Programs\Python\Python313\python.exe` (Git-Bash `python3` lacks capstone/etc.)
- Genuine WiiU refs: `...\Testing enviroment\wiiu_ref\` (mp_raid_english.ff = d6e41ce3, genuine ipak, etc.)
- Rebuild cmd per test: `OAT_REWRITE=1 OAT_IGNORE_SIG=1 [flags] Unlinker.exe --list <map>.ff`  → `<map>_rewrite.ff`, then `python wiiu_ff.py pack <map>_rewrite.ff mp_raid out.ff`
- Cemu slot: user copies `out.ff` → `E:\Wii U Black ops 2\content\english\mp_raid.ff` (⛔ do not edit other files in E:\ game folders; copy sources out first).

⚠️ SHARED-FILE COORDINATION: all three fixes edit the write path (`ContentWriterT6.cpp`
and neighbors), each in a DIFFERENT asset handler. There is NO git here. To run in
separate instances safely, give each track its OWN COPY of `tools\ref_oat\` (build
independently), or serialize the merges into the canonical tree. Do not have two
instances editing the same `ContentWriterT6.cpp` at once.

---

## PARALLELISM MAP
- **Track A — Inline texture → IPAK streaming** … independent, START NOW. (Unblocks PC/DLC maps.)
- **Track B — Custom-map world-asset fault bisection** … independent, START NOW.
- **Track C — GSC transcode in write path** … IMPLEMENT NOW (independent code), but
  END-TO-END VERIFY only after Track B (dust2 must load before its scripts can run).
- **Track D — PC .sabs/.sabl sound converter** … ALREADY RUNNING (separate handoff).

A, B, D are fully concurrent. C is concurrent to implement; its final verification
waits on B. Recommended: 2 instances = one on A, one on B; fold C into whichever
finishes first, then verify C once B lands.

---

## TRACK A — Inline texture → IPAK streaming  (fixes PC/DLC OOM)
**Problem:** PC fastfiles embed every GfxImage's pixels inline. `ConsoleWriterT6`
writes those pixels inline (and untiled). Genuine WiiU maps instead mark images as
*streamed* and pull pixels from a companion `.ipak`, so the DB heap stays small.
Inline pixels overflow the fixed WiiU DB pool → `Sys_Error("Out of memory")`.

**Fix:** In the console image write path, for each GfxImage that has inline pixels:
1. **Tile** the pixel data to WiiU GX2 tiling via `gx2_texture.tile()` (tileMode per
   format; see `wiiu_ref\gx2_texture.py`).
2. **Emit** the tiled blob into a companion `<mapname>.ipak`, keyed exactly like
   genuine: `combinedKey = nameHash<<32 | dataHash`, per-part `crc32(payload)&0x1FFFFFFF`,
   BE (WiiU stores nameHash first). Reuse `wiiu_ref\ipak.py` (write_ipak, parse_iwi).
3. **Rewrite the GfxImage** in the zone: set the streamed/loadedSize fields so the
   engine streams from ipak; clear inline `pixels`/`baseSize` so nothing is embedded.
   (See ConsoleWriterT6 ~line 371 `inlinePixels = streaming==0 && pixels && baseSize>0`
   and ~line 397 `WriteDataInBlock(image->pixels, image->baseSize)` — invert this to the
   streamed path.)
**Inputs/refs:** genuine `wiiu_ref\mp_raid.ipak` for exact key/layout; earlier IPAK
findings (`ipak_key_findings.md`); `gx2_texture.py` tile/detile; pixel-identity test
(detile(WiiU payload)==PC IWI mip).
**Deliverable:** patched write path + `mp_raid.ipak` emitter. Rebuild PC Raid →
`mp_raid.ff` + companion `mp_raid.ipak`; user drops both in `content\` and `content\english\`.
**Done when:** PC Raid loads past DB-load (no OOM); textures may still need tiling
polish but no crash.

## TRACK B — Custom-map world-asset fault  (fixes dust2 hard crash)
**Problem:** dust2 hard-faults ~17 ms into DB-load. Ruled OUT: scripts (no-GSC build
still crashed), textures (too early), signature, codec. dust2 asset makeup: 6 script,
6 footsteptable, 1 rawfile, 1 **comworld**, 1 **mapents**, 1 **clipmap**, 1 **gameworldmp**,
1 **gfxworld**, 1 xmodel, 1 skinnedverts, 2 techset, 126 material, 130 image. The fault
is almost certainly in a **world asset's console write layout** (comworld / gameworldmp /
mapents are less-exercised than gfxworld/clipmap, which were validated on retail).
**Method:**
1. Bisect with `OAT_LIMIT_ASSETS=N` (build zone with only first N assets), rebuild,
   user load-tests, to bracket the faulting asset index. Link order from
   `OAT_IGNORE_SIG=1 Unlinker --list dust2.ff`. (scripts are 1-6, comworld ~14,
   mapents ~15, etc.)
2. In parallel, STATIC check: dump the suspect asset and compare its console byte
   layout to a genuine WiiU map's same asset type (structural comparator /
   `zone_validate.py`, `OAT_DUMP_CLIPMAP`). Look for wrong struct size, a pointer/
   offset written where genuine has an inline count, or a dropped/!dropped console
   member mismatch.
3. Fix the offending console writer in `ContentWriterT6.cpp` (add the missing
   console layout / IsConsoleRealDrop / explicit-offset handling for that type).
**Source of truth:** genuine WiiU dust2 doesn't exist, but genuine retail WiiU maps
(mp_raid etc.) have comworld/mapents/gfxworld to compare struct layout against.
**Deliverable:** identified asset + writer fix; dust2 loads past 17 ms.
**Done when:** dust2 reaches texture streaming / map load instead of the 17 ms fault.

## TRACK C — GSC transcode in write path  (scripts survive the port)
**Problem:** write path writes PC GSC bytecode UNCHANGED into the BE zone (no transcode
exists for `scriptparsetree` in ZoneWriting — verified). WiiU script VM faults on
little-endian bytecode. Only DROP currently works.
**Fix:** Wire the already-solved PC→WiiU GSC transcode into `ContentWriterT6`'s
`scriptparsetree` writer: byte-swap the GSC header + tables + cseg operands and
recompute each export's crc32 (logic in `wiiu_ref\gsc_inject.py` / `gsc_diff.py`;
see memory note on GSC transcode). Apply per script asset at write time instead of
copying raw bytes.
**Deliverable:** write path emits WiiU-valid GSC automatically (no OAT_DROP_GSC needed).
**Verify:** after Track B lands, rebuild dust2 WITH scripts → loads AND scripts run
(map logic/spawns work). Until B lands, unit-verify by transcoding one PC script and
diffing against a genuine WiiU script of the same name.
**Done when:** a PC map ported with scripts boots and runs its GSC on WiiU.

---

## After the 3 fixes
- PC retail + **PC DLC** maps should port (Fix 1 is the DLC unblock; DLC maps are
  well-formed like retail, so likely need only A, maybe C).
- Custom maps need A + B + C.
- (Optional alt track: user also has **360 DLC files** — a console-to-console port is
  possible but requires a new 360 unlinker + Xenon→Latte texture/vertex transcode;
  deprioritized because the PC path reuses all existing tooling and the DLC is already
  available in PC form. Keep as fallback only.)
```
```
