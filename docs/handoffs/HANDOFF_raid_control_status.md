# HANDOFF — raid control test: status update for the main session

Date: 2026-07-11. Context: a long debugging session that started on the mp_skate boot crash
and pivoted to a **raid control experiment**. This doc is the current-state summary; the
companion `HANDOFF_xmodel_inline_image.md` is the actionable next-steps work order.

## TL;DR
- The from-PC no-backbone pipeline does **not** produce a loadable map — proven on **raid**,
  a stock map where we have the genuine console zone as ground truth. So the boot failure is
  **pipeline-wide, not skate-specific.**
- **Root cause (ghost-free, verified vs genuine): our XModel converter DROPS large
  inline-material images.** The skybox model `skybox_mp_raid` emits 15,380 B vs genuine
  1,588,228 B — it drops its ~1.5 MB inline skybox texture. 36/440 XModels under-emit 3.68 MB
  total. Skybox renders every frame during the load screen → dropped texture → GPU samples
  absent data → wild pointer in Cemu's GPU path = raid's crash (dump 25192). Almost certainly
  hits skate too (skate has a skybox).
- **Fix path:** complete the XModel inline-material image emit. See the companion handoff.

## What was PROVEN this session (trust these)
1. **Both authored raid AND skate crash.** raid dump `C:\CemuFullDumps\Cemu.exe.25192.dmp`
   (Cemu-host wild-pointer scan, GPU/recompiler path). skate dumps 36196/37608 (guest
   NULL-string deref in a `char==','` parser — see [[skate-boot-nullderef-not-layout]]).
2. **The deploy harness is VALID.** Packed genuine `mp_raid_genuine.zone` through our packer,
   deployed to the update partition, and it **runs** on Cemu (no crash). So packer +
   update-partition override + deploy path are all correct → authored-raid's crash is our
   converted content, not a deploy artifact.
3. **Root cause = dropped XModel inline-material images** (skybox +35 others, −3.68 MB;
   byte-vs-genuine, cross-checks the per-type XModel −3.7 MB total).

## What was RULED OUT (leads that dissolved under clean measurement — do NOT re-chase)
- **Image track "broadly under-emitted"** → too broad. Standalone-**Material** inline images
  emit fine (`gfximage_probe.py`: authored & genuine raid both = 672 mats, 509 inline images,
  modal 328). Only **XModel-inline-material** images are dropped (different code path).
- **Pointer bake broken / OOB pointers** → refuted for LIVE fields. Correctly-aligned XModel
  `materialHandles` (game follows these) = 0 OOB, 329/333 valid. The OOB words I first found
  are at dangle/interior positions the allowlist already treats as boot-safe.
- **StringTable / KeyValuePairs / clipMap_t / GameWorldMp / ComWorld / config** → all match
  genuine; not the bug.
- **Sound files** → skate crashed before any skate `.sabs/.sabl` was even loaded.

## GHOST TRAPS hit this session (methodology warnings)
- **`LS.simulate` re-walk is UNRELIABLE for per-asset sizes across different policies**
  (GEN_POLICY vs gfx_skip=0). It mis-attributes body boundaries → false "292 misaligned",
  false per-type Material/GfxImage under-emission. **Use the assemble's `out_assets` emitted
  bodies (exact bytes) paired against genuine `co_by`, not two independent walks.**
- **Value-range pointer scans are ~77% false positives** — floats densely populate the
  0xA0–0xBF alias byte-range. Never classify a word as a pointer by value alone.
- The `raid_oracle_control` gate PASSES by **allowlisting** pointer mismatches in ALLOW_DIFF
  types (XModel/techset/Snd) **without bounds-checking them**. "GATE PASS" never validated
  pointer targets or body sizes in those types — a real blind spot (harmless for live ptrs as
  it turned out, but be aware).

## The harness — build / deploy / boot-test (all verified working)
```
cd native_linker
# build authored raid from PC (genuine-derived policy; writes mp_raid_authored.zone):
python produce_container.py                 # == raid_dryrun(); GATE PASS, unresolved 0
python ../WiiU_FF_Studio/wiiu_ff.py pack mp_raid_authored.zone mp_raid mp_raid_authored.ff
# deploy to the UPDATE partition (overrides E:\ base mp_raid.ff; NEVER write under E:):
cp mp_raid_authored.ff "C:/Users/Tony - Main Rig/AppData/Roaming/Cemu/mlc01/usr/title/0005000e/1010cf00/content/english/mp_raid.ff"
# boot raid from normal map-select (stock map, no DLC gate). Revert = delete that one file.
```
- `wiiu_ff.decrypt(ff)` returns `(hdr, zone, n)` — roundtrip check = `d==zone`.
- Cemu `log.txt` (AppData/Roaming/Cemu) is overwritten every launch — read BEFORE relaunch.
  Full dumps: WER LocalDumps DumpType=2 → `C:\CemuFullDumps\Cemu.exe.<pid>.dmp` (PID-named,
  never overwritten).
- Deployed right now in the update slot: **genuine raid** (from the harness-validation test).
  Re-deploy `mp_raid_authored.ff` when resuming, or delete for stock.

## Key files
- `native_linker/produce_container.py` — `author_zone()`, `raid_dryrun()` (the control build).
- `native_linker/produce_nobackbone.py` — `assemble_zone()`; emit dispatch; techset substitution.
- `native_linker/raid_oracle_control.py` — byte-diff-vs-genuine gate; `console_spans()`.
- `native_linker/xmodel_pc.py` / `xmodel_convert.py`, `wiiu_ref/xmodel_probe.py` — XModel path
  (the fix target — see companion handoff).
- `wiiu_ref/mp_raid_genuine.zone` — ground-truth console zone. `PC ff/mp_raid.zone` — PC input.
- Dumps: skate 36196/37608, raid 25192 in `C:\CemuFullDumps\`.

## Where skate stands relative to this
Skate's own crash (guest NULL-string deref in a CSV parser) was being chased blind (no console
reference). The raid control test is the better path: fix the pipeline against raid ground
truth, then re-test skate. The dropped-skybox-texture finding plausibly explains skate too —
verify after the XModel fix lands on raid.
