# FINDINGS — skate boot #1: dump-measured runtime calibration (the gfx_skip breakthrough)

## Summary
mp_skate's authored zone **LOADS** on Cemu (fastfile format/decompress/container all accepted) but
**null-crashes during map-init**. Root cause: the pass-3 loader-sim that bakes the zone's pointers
(`our_policy=None`) computes each asset's RUNTIME block-5 offset **off by ~1.2 MB** vs where the real
console loader places it, so every post-GfxWorld alias points into garbage. The console runtime band
(the project's hardest open item, "gfx_skip") is NOT count-derivable — but it does NOT need to be
derived: **the crashed process's full memory dump is the ground-truth runtime layout, and we measure
it directly.**

## The crash (three identical repros)
- `mp_skate.ff` opens from the DLC path, streams in (262 KB FSReadFile chunks), accepted.
- Black-screen crash on the load/map-init thread (last GX2 draws = loading-screen quads only).
- Cemu host-crash (`0xC0000005` access-violation READ, guest addr 0 / NULL) in JIT'd PPC code.
  The game's own crash handler can't run — `coreinit.OSSetExceptionCallback` is unsupported in Cemu.

## Getting a full memory dump (Cemu's "Full" setting does NOT produce one)
Windows WER LocalDumps, per-app, DumpType=2 (full). Admin cmd:
```
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\Cemu.exe" /v DumpFolder /t REG_EXPAND_SZ /d "C:\CemuFullDumps" /f
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\Cemu.exe" /v DumpType   /t REG_DWORD    /d 2            /f
reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\Cemu.exe" /v DumpCount  /t REG_DWORD    /d 5            /f
```
Repro → ~3.3 GB `C:\CemuFullDumps\Cemu.exe.<pid>.dmp`. (Turn OFF the GDB stub first — it's on port
1337, single-connection-per-launch, minimal protocol; more trouble than the dump.)

## Reading the dump (minidump format, no external tools)
- Header `MDMP` @0; `(nStreams, dirRVA)` @8; directory = nStreams × (type,size,rva).
- Exception stream = type **6**: ThreadId(4), align(4), then ExceptionCode(4), Flags(4),
  Record(8), **ExceptionAddress=IP**(8), NumberParams(4), align(4), Info[15]×8
  (Info[0]=0 READ/1 WRITE/8 EXEC, Info[1]=faulting address).
- Guest RAM = **Memory64List** stream = type **9**: (count(8), baseRVA(8)), then count×(startVA(8),
  size(8)); the i-th range's bytes are at file offset baseRVA + Σ prior sizes. Guest base =
  log line "Init Wii U memory space (base: 0x…)"; keep ranges with base ≤ VA < base+4 GB (~1.5 GB).

## Measuring the runtime shift (the method)
1. Pick a UNIQUE needle from `native_linker/mp_skate_authored.zone` (the exact zone the deployed
   `.ff` was packed from). Good anchors: a 40 B asset-name chunk from the script-string table
   (block-5 offset ≈ 3108, effectively pre-shift); `mp_global_intermission` (post-gfx).
2. Search guest ranges for each needle; keep the copy inside the zone buffer window [base, base+~110 MB].
3. `block5_base = guest(anchor) − anchor_stream_b5`.
   `runtime_shift(asset) = (guest(asset) − block5_base) − asset_stream_b5`.

## The numbers (2026-07-11, dump Cemu.exe.27476.dmp, guest base 0x20896ae0000)
- str-anchor (stream_b5 3108) → post-gfx asset: **runtime shift = +1,078,795 B**.
- Shift is **distributed** (grows through the zone: ~+20 K @1 MB, ~+192 K @20 MB, ~+763 K @50 MB,
  ~+1.08 M @ end) — dominated by per-asset structural runtime overhead, NOT a single GfxWorld jump.
  (This is why count-based gfx_skip regressions failed at ±184–500 K.)
- SIM (`our_policy=None`, pass-3) predicts ~−145 K at the same span ⇒ **baked pointers off by ~1.2 MB.**

## Fix path (calibration, in progress)
1. Re-author verify: fresh `author_zone(...)` must reproduce `mp_skate_authored.zone` byte-for-byte
   (determinism), so the sim's omap corresponds to the dumped layout. Caveat: `mp_global_intermission`
   is in BOTH GameWorldMp AND MapEnts — disambiguate by asset span.
2. Measure real runtime offsets for a spread of assets across the zone (unique needles) → the
   correction function `measured(stream_b5) − sim_predicted(stream_b5)`.
3. Make the pass-3 sim reproduce the measured layout (calibrate the runtime policy, or build the
   runtime map directly from the measurements) so every asset lands where the loader puts it.
4. Rebuild skate → redeploy → boot. The dump loop is the verification oracle from here.

See memory `skate-boot-1-result`, `container-author`; BOOT_SHEET.md.
