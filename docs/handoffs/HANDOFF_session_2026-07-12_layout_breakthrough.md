# HANDOFF — 2026-07-12 session: GfxWorld crash = LAYOUT not content; skate measure→rebake WORKS

Long session. Started on the XModel inline-image handoff, pivoted through a full content-bisection of the
raid boot crash, PROVED the GfxWorld crash is the runtime layout (gfx_skip band) not converter content, and
closed the measure→rebake loop on skate (which ADVANCED past the layout crash). This doc is the full record.

═══════════════════════════════════════════════════════════════════════════════
## TL;DR — the arc
═══════════════════════════════════════════════════════════════════════════════
1. Skybox inline-image drop is NOT the boot crash (the XModel handoff premise is DEAD).
2. Container authoring is PROVEN correct: ALL3 (100% genuine bodies in our container) BOOTS.
   → every remaining raid crash is a CONVERTER bug, mappable by content-bisection.
3. Built content-bisection harness (_bisect.py + produce_nobackbone BISECT_* hooks + genuine transplant).
4. SndBank: found + fixed the endian bug (aliasCount read as 1.6e9) + the .sab checksum embed; STILL
   crashes = blanket _swapw corrupts SndAlias(100) sub-u32 fields. Field-aware fix = the pinned TODO.
5. author_english_bank is broken (opens a garbage .sabs) — confirmed via ALL2(crash) vs ALL3(boot).
6. **GfxWorld crash = RUNTIME LAYOUT, not region content** — PROVEN by clean same-size injection.
7. Applied skate measure→rebake loop → skate ADVANCED past the layout crash (+0x20b6aa) to the SAME
   SndBank crash raid has (+0x3817ce). gfx_skip/layout is SOLVED on skate.

Critical path now CONVERGED: the SndBank field-aware SndAlias fix unblocks BOTH raid and skate.

═══════════════════════════════════════════════════════════════════════════════
## KEY METHODOLOGY GOTCHAS (do not relearn these)
═══════════════════════════════════════════════════════════════════════════════
- **Crash rip: use Cemu's LOG stack rip, NOT the WER minidump ExceptionStream.** The WER ExceptionStream
  records a FIRST-CHANCE handled exception (e.g. a strlen at +0xfd806c); Cemu's own crashlog (log.txt
  "Exception 0x… at +0xXXXXXX") is the FATAL fault. They differ. Early this session I wasted effort
  analyzing the WER strlen before realizing the fatal was +0x3817ce.
- **+0x3817ce is a SHARED symptom, not a fingerprint.** SndBank, author_english_bank, AND our GfxWorld all
  trigger the identical +0x3817ce (AX voice frame-callback walking a corrupted list at guest 0x10e89490,
  R13=0x1c8, R15=0x1d8, RSI=0x00b8dd…). Crash ADDRESS ≠ which converter. Only ISOLATION tells the culprit.
- **Content-bisection is the validation gate.** "byte-matches genuine offline" and "gate-green/EOF-EXACT"
  do NOT catch integration/layout bugs. Only a boot does. A converter is not "fixed" until an isolated
  bisection boot clears it. This is why prior "DONE" converters were secretly broken.
- **Same-size injection holds layout constant.** To separate content bugs from layout bugs: start from
  GENUINE GfxWorld (loads) and inject OUR same-size regions at the SAME offsets (zero layout shift). If it
  still boots, that region's content is cosmetic. This is how we proved layout-not-content.
- **Dumps: WER LocalDumps DumpType=2 → C:\CemuFullDumps\Cemu.exe.<pid>.dmp (PID-named, never overwritten).
  Cemu log.txt is overwritten each launch — read BEFORE relaunch.** Guest base = log "Init Wii U memory
  space base"; per-dump base differs (ASLR). Parse Memory64List = stream type 9.

═══════════════════════════════════════════════════════════════════════════════
## THE GfxWorld BREAKTHROUGH (the big one)
═══════════════════════════════════════════════════════════════════════════════
**Proven: the GfxWorld +0x3817ce crash is the runtime LAYOUT / gfx_skip band, NOT converter content.**

Evidence (raid, all builds = genuine everything else, only GfxWorld varies):
- gfxtest2 (our GfxWorld, verified only-GfxWorld-differs) → CRASHES.
- gfxSI (our GfxWorld + genuine streamInfo spliced) → CRASHES.
- gfxIMG (our GfxWorld + genuine material/image regions, 32KB short) → CRASHES.
- **ourDATA2 (GENUINE GfxWorld + our same-size regions injected at same offsets) → BOOTS** (cosmetic only).
⇒ every same-size region's CONTENT is cosmetic. To boot you need genuine streamInfo AND genuine cells AND
genuine images — the three SIZE-differing regions. It's the SIZE/interior-structure, not the bytes.

Mechanism: GEN_POLICY bakes runtime addrs with gfx_skip=919836 (added to BLOCK_VIRTUAL after GfxWorld,
loader_sim.py:329), split under co_structural_gfx into planes_skip=750191 (@dpvsPlanes) + matmem_skip=234650
(@materialMemory) + end_residual (gfxworld_events.gfxworld_console_events, positions from
parse_gfxworld_console). Our 3 size-differing regions are INHERENTLY different from genuine: streamInfo
SYNTH (1023 trees/4668 refs vs genuine 785/9751, −8908B), cells console-REBUILDS aabb trees (−12288B),
images STUBBED (−394KB). Each shifts interior gap positions & the true GX2 alloc, but GEN_POLICY assumes
genuine's → downstream runtime addrs wrong → wild ptr. = the known "boot risk #1: gfx_skip band unmodeled,
not count-derivable, ±184K".

Raid measurement (dump 30096, our GfxWorld): GfxWorld and the next asset (GameWorldMp) landed 84MB apart in
guest MEM2 (base 0x2b21fff0000) — a huge runtime gap vs the 0.9MB we baked. Naive single-pair band measure
is unreliable (layout isn't simple contiguous+gap) → needs the full per-asset measured_rtmap pipeline.

RAID CAVEAT: raid can't resolve its GfxWorld images (no PC raid ipak on disk) so its GPU band inherently ≠
genuine's 919836 — GEN_POLICY is FUNDAMENTALLY WRONG for our raid GfxWorld and no policy tweak fixes the
missing pixels. Raid was the right CONTROL (genuine ground-truth) to prove the diagnosis; it can't be the
vehicle to solve it. SKATE is the vehicle (images resolve, uses derive/measure).

═══════════════════════════════════════════════════════════════════════════════
## SKATE MEASURE→REBAKE LOOP (WORKED — the deliverable moved)
═══════════════════════════════════════════════════════════════════════════════
Repeatable loop: rebuild → boot → measure real layout from dump → rebake with override_rtmap → boot.
1. `python produce_container.py skate` — now passes image_ipak=../skate_artifact/mp_skate.ipak → GfxWorld
   22.89MB with resident lut. → mp_skate_authored.zone (99.85MB, REWALK EOF-EXACT, unres 0). Pack →
   mp_skate_imgfix.ff. BOOT → CRASH +0x20b6aa (pointer-reloc/layout crash) → dump 18896.
2. MEASURE: regenerate _skate_simmap.pkl (loader_sim.simulate(zone,gfx_skip=0) spans; ae=23287; 801 spans),
   then windowed unique-needle search in dump 18896 → _skate_realmap.pkl (408/801 assets; GfxWorld rt start
   +1,252,389 = the ~1.2MB gfx band). See the inline scripts I ran (measure logic mirrors _measure_real.py:
   anchor = script-string region Z[o+200:o+240] where o=64+string_count*4; base=(anchor_hit)-anc_b5).
3. REBAKE: author_zone(..., override_rtmap=MeasuredRuntimeMap('_skate_simmap.pkl','_skate_realmap.pkl')) →
   0 simfallback, max_rt 101.1MB, block-5 sized to cover it. Pack → mp_skate_measured.ff.
4. BOOT mp_skate_measured.ff → ADVANCED past +0x20b6aa to +0x3817ce (dump 26244, during FSReadFile
   streaming) = the SAME SndBank/AX-voice crash as raid. ⇒ LAYOUT SOLVED on skate.

Coverage was 51% (vs ~83% on the prior working skate run) — if a future rebake needs it, widen the
needle window / raise the tries cap in the measure script. Skate deploy = mlc01/usr/title/0005000c/
1010cf00/content/0010/english/mp_skate.ff. USE `python` not `python3` (numpy in GfxWorld emit).

═══════════════════════════════════════════════════════════════════════════════
## CODE CHANGES MADE THIS SESSION (all in native_linker/ unless noted)
═══════════════════════════════════════════════════════════════════════════════
- **smalls_convert.py :: convert_sndbank** — REWROTE from verbatim-copy to FULL ENDIAN-AWARE: walks like
  sndbank_probe.parse_sndbank, `_swapw` (per-4B word swap) each word-region, strings/zeroed-data verbatim.
  Fixes aliasCount/radverbCount (were LE→console read 1.6e9). PLUS: SNDBANK_HEAD_OVERLAY +
  SNDBANK_CKSUM_BLOCKS=[(0x830,16),(0x940,12),(0x1150,20),(0x1264,8)] overlay the deployed .sab's checksum
  blocks (engine Sys_Error's on mismatch @body+0x830 = .sab hdr @0x38). NOT block +0x20 (=streamAssetBank
  zone* ptr; overlaying it desyncs the string walk). ⚠ STILL INCOMPLETE: blanket _swapw corrupts SndAlias
  sub-u32 fields → NEEDS field-aware SndAlias/SndAliasList/SndRadverb(100)/SndDuck(76) conversion (the TODO).
- **produce_nobackbone.py** — added module globals BISECT_LOG / BISECT_MAP (default None = no-op) + a hook
  in the emit loop (after `body,why = emit_one(...)`): BISECT_LOG captures {pc_off: (root, len)};
  BISECT_MAP {pc_off: genuine_body} substitutes bodies verbatim (clears conv.xc_scaled/xc_fine/regions).
  This is the content-bisection engine. TEMPORARY/reversible.
- **gfxworld_gx2.py :: conv_tail_material** — image-source resolver now handles RAW-blob returns (resident
  lut has no IWI header): if iwi lacks width/height, take dims/format from the console img_body's GX2 header
  (word1=w @off+4, word2=h @off+8, word5=gfmt @off+20, LE). Fixes the tail-lut resolving to 262KB (was 486
  stub). Guard `if iwi is None or not iwi.get('blob')`.
- **produce_container.py** — added `_make_pc_image_source(ipak_paths)` (PcImageSource + RAW-blob fallback
  for non-IWI entries like the lut), and `author_zone(..., image_ipak=None)` which sets MC.IMAGE_SOURCE.
  Skate __main__ branch now passes image_ipak='../skate_artifact/mp_skate.ipak'. (raid has NO PC ipak.)

Scratch/test scripts (native_linker/, keep as reproducers): _bisect.py (content-bisection driver:
`python _bisect.py ALL|NONE|Root1,Root2` — transplants genuine bodies for those roots; pairs positionally,
or nearest-size for count-mismatched roots like SndBank's english insert), _build_transplant.py
(skybox/clean/all XModel transplant), _dump27508.py + inline dump scripts (Memory64List + capstone disasm),
_measure_real.py (skate realmap measurement, dump path hardcoded — update per run).

═══════════════════════════════════════════════════════════════════════════════
## BUILD ARTIFACTS (native_linker/*.ff) — what each tests + RESULT
═══════════════════════════════════════════════════════════════════════════════
RAID (deploy: mlc01/usr/title/0005000e/1010cf00/content/english/mp_raid.ff):
- mp_raid_bisect_ALL2.ff  = 100% genuine bodies, our container → LOADS (proves container authoring OK).
- mp_raid_bisect_ALL3.ff  = ALL2 + genuine english insert → LOADS (author_english_bank is the ALL2 bug).
- mp_raid_bisect_SndBank.ff = genuine SndBank only → +0x3817ce GONE, revealed +0x20a436 (SndBank = a culprit).
- mp_raid_sndfix.ff / _sndbank2.ff = our SndBank endian+checksum → STILL +0x3817ce (field-aware needed).
- mp_raid_gfxtest2.ff  = genuine everything + OUR GfxWorld only (verified) → CRASHES (GfxWorld is a culprit;
  my earlier "+0x20a436 = GfxWorld" was WRONG — GfxWorld crashes +0x3817ce; +0x20a436 is another converter).
- mp_raid_gfxSI.ff  = our GfxWorld + genuine streamInfo → crashes.
- mp_raid_gfxIMG.ff = our GfxWorld + genuine material/image regions → crashes.
- mp_raid_ourDATA.ff / ourDATA2.ff = genuine GfxWorld + our same-size regions → **BOOTS** (content cosmetic).
SKATE (deploy: 0005000c/…/0010/english/mp_skate.ff):
- mp_skate_imgfix.ff  = image fix, derived policy → CRASH +0x20b6aa (layout) → dump 18896.
- mp_skate_measured.ff = image fix + measured override_rtmap → **ADVANCED** to +0x3817ce (dump 26244).

Crash-dump reference (C:\CemuFullDumps\): 30096=raid gfxtest2; 14508=raid gfxSI; 10984=raid gfxIMG;
18896=skate imgfix (layout crash); 26244=skate measured (SndBank crash).

═══════════════════════════════════════════════════════════════════════════════
## OPEN WORK (prioritized)
═══════════════════════════════════════════════════════════════════════════════
1. ⏳ **SndBank field-aware SndAlias conversion** (CRITICAL PATH — unblocks BOTH raid & skate +0x3817ce).
   convert_sndbank's blanket _swapw corrupts SndAlias(100) sub-u32 fields (u16 vol/pitch, u8 flags, inline
   chars "amb_"→"_bma"). FIX: derive each field's endian type empirically — for each 4-byte-word position in
   SndAlias, check across ALL 2656 raid aliases whether genuine == swap32 / swap16-pair / verbatim of PC,
   build the field-type template, apply it (also SndAliasList(20), SndRadverb(100), SndDuck(76)). Defer the
   console name-hash (a4xx values; NOT r_hash_string of any bank name → console-specific, lookup-only,
   non-crash). Byte-validate on raid vs genuine main bank (12,967,232 B). Then rebuild both maps.
2. Cosmetic GfxWorld byte-bugs (non-crash, byte-fixable, same bug-class as SndAlias): lightGrid.rawRowData
   is a VARIABLE/tagged format treated as verbatim (16B-row [u16×4 swap2][u32 swap4][4 verbatim] for most
   rows but row-format varies — needs a proper row parser keyed by rowDataStart); dpvs.surfaces ZEROES the
   surface cull bounds @0-31 (conv_surface drops them). draw.indices 2.7% (minor).
3. After SndBank fix: re-run skate measure→rebake (rebuild changes layout → re-measure). Iterate on the
   next crash. Raise measurement coverage if needed.
4. Raid GfxWorld can't be fully boot-validated without the PC raid ipak (image gap). Not a blocker for
   skate. If raid full-boot is ever wanted, need to source the PC raid image ipak.

═══════════════════════════════════════════════════════════════════════════════
## MEMORY FILES UPDATED THIS SESSION (persist across compaction)
═══════════════════════════════════════════════════════════════════════════════
- gfxworld-crash-is-layout-not-content.md (NEW — the breakthrough + skate loop).
- xmodel-inline-image-transplant.md (SndBank bisection, checksum, SndAlias TODO, skybox-red-herring).
- gfxworld-resident-image-gap.md (image-source wiring + tail-lut fix).
- MEMORY.md index has ★★ line for the layout breakthrough. The ⏳ SndBank TODO is pinned there.
