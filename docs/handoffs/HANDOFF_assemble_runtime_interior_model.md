# HANDOFF — ASSEMBLE: runtime-allocation + interior-alignment model → gate PASS

SUPERSEDES the residual items (§4/§5) of `HANDOFF_assemble_gate_close.md`. That session
(2026-07-09/10) completed its items 1–3 and root-caused the rest to ONE named model gap,
measured below. Read `FINDINGS_loader_sim_pointer_model.md` first for the base model.

## What the previous session finished (state you inherit)
- **Genuine-side walk CLOSED**: `loader_sim.simulate_stream` dispatches `clipMap_t` →
  `native_linker/clipmap_console.py`, `SndBank` → `sndbank_probe`, `XAnimParts` →
  `xanimparts_probe`. Genuine raid walks ALL 889 assets to EOF with **zero leftover**
  (the "13 MB tail" was the two SndBanks: `mpl_raid.english` 6,663 — the console-only
  insert — + `mpl_raid.all` 12,967,232 incl. an 11.5 MB inline loadedAssets blob; the
  physical block-2 header size 12,976,128 ≈ that blob). ST-dedup calibration unchanged
  (raid 7009/6, dockside 9769/9, transit 2821/0). Gate quarantine retired.
- **Converters integrated, all ≥2-map validated byte-exact (mod pointers/drift):**
  `native_linker/clipmap_convert.py` (NEW; raid 4,412,940 + dockside 2,910,696, HARD=0),
  `smalls_convert.convert_gameworldmp` (== chase probe output on raid + dockside),
  `smalls_convert.convert_scriptparsetree` (gsc_swap; SPT now 13/13 **exact** at the gate).
- **Gate upgrades** (`raid_oracle_control.py`): HARD_CLASS word predicates (clipMap
  float-drift ≤128 same-exponent; DestructibleDef |Δ|==1) — all six DD pairs now hard=0;
  ALLOW_DIFF += Glasses, SndBank; SndBank pairs by BANK NAME (`.english` = the insert);
  no-console-pair → aliased-twin rule (both former no-pairs PASS); content-equality
  fallback in `semantic_diff` for cross-asset dedup (both sides fetch 8 target bytes).
- **Assemble fixes** (`produce_nobackbone.py`): unresolved pointers now emit TAGGED
  poison (0xBF0xxxxx) instead of PC-value passthrough (passthroughs masqueraded as
  wrong pointers); PC XAsset-array slot base now `align8` (mp_skate's 573→8.5k
  "outside" unresolved were ALL slot refs missed by the unshifted base — raid is
  phase 0, skate isn't: raid-luck-masking again); pass-3 sim takes authoritative
  per-asset lengths (`known_len`) and RESYNCS on parse gaps instead of desyncing
  (our 59.7 MB PC-copy SndBank broke the walk and swallowed all later ranges).

## Gate as of handoff (raid)
`{ptr-equivalent: 6, exact: 127, allowlisted: 737, aliased-twin: 2, VIOLATION: 9}` —
all 9 violations are **pointer-only** (hard=0 everywhere except 4 stray drift-window
bytes in clipMap): DestructibleDef ×6 (ptrbad 5..93, the ~220 geometry-share),
ComWorld (3), GameWorldMp (526), clipMap (28,191). unresolved = GfxWorld-only + 2 tagged.

## THE ONE REMAINING GAP (measured, not conjecture)
Genuine alias values encode the REAL loader cursor, which includes:
1. **RUNTIME-block allocations** consuming virtual space with no file bytes
   (GfxWorld's runtime regions dominate; GWMP basenodes 16×(nodeCount+128); clipMap
   dynEnt pose/client/server/coll lists + ropes), and
2. **per-allocation alignment inside delimiter-walked (verbatim) assets** — the
   documented "linear interior approximation" caveat, now quantified.

Evidence (scratch scripts existed as `measure_shift*.py`, trivially recreated):
- Genuine raid GWMP tree child-aliases (516, dedup'd subtrees): shift ≈ **+933.7 K**
  vs sim (±112 plateau from the 16-stride autocorrelation).
- Genuine raid SndBank SndAlias name→list-name anchors (EXACT targets):
  bank[0] shift = **936,993/936,994** (±1 split = string-align rounding);
  bank[1] spreads **940,400..940,760** across its 12 MB → interior drift ≈ 360 B.
- PC side mirrors it ~20× larger: PC GWMP self-refs invert ~21 MB too high (PC
  GfxWorld's runtime DPVS etc.), landing inside the huge PC SOUND span — that was the
  gate's "(SOUND,0)" mis-resolution class.

## The work
1. **Event walkers** for the delimiter types: emit an ordered allocation-event list
   (rel_file_off, size, align; plus runtime-skip events) per asset. clipMap: adapt
   `clipmap_probe.walk` (endian-parametrized, already visits every allocation; aligns:
   structs 4 / u16 arrays 2 / strings+bytes 1). GWMP: adapt
   `smalls_convert.convert_gameworldmp`'s walk (nodes, per-node links, basenodes SKIP
   16×(n+128), vis, smooth, tree recursion incl. u16 leaf arrays align-2). Because PC
   and console serialize byte-identically, ONE relative event list per asset serves the
   PC sim, the genuine-console sim, and our-stream sim.
2. **Wire into loader_sim**: replace the verbatim register-once dispatch with an
   event replay (align runtime cursor per event; register each segment; advance;
   runtime-skips advance without file bytes). This automatically fixes
   produce_nobackbone's pass-3 encodings AND the gate's both-side resolvers.
3. **GfxWorld runtime total**: per-zone constant, EMPIRICALLY derivable from the
   zone's own SndBank anchors (blind-usable: measure on the PC zone for pc_inv; on the
   genuine zone for the gate). Apply as a skip event at GfxWorld end. Interior refs
   INTO GfxWorld stay tagged/pending Track F (which should eventually produce the real
   alloc list).
4. **dynEnt list sizes**: solve from anchors before/after clipMap's constraints
   section (raid dynEntCount[0]=580); consider they may allocate in a non-virtual
   block (skip=0) — the anchors decide.
5. **XModel/techset interiors**: the same drift exists pre-GfxWorld (string allocs in
   440 XModels / 224 techsets); the ST calibration bounds it as small there. Check
   whether DD geometry-share (~220) clears with content-compare once gen deltas are
   exact; if not, add marks to `xmodel_convert`.
6. Re-run gate → expect clipMap/GWMP/ComWorld/DD to go ptr-eq → **declare PASS** with
   the named allowlist classes; re-run skate assemble → unresolved must be GfxWorld-only
   (+ tagged oddballs; the 3 refs at pc_b5≈534,945,593 — beyond the PC file — are the
   oddball class, classify them).

## SMALL ADD-ON (main session, 2026-07-10): Material drawSurf endian bug — fix here, you own the file
`material_convert.convert_material` packs the drawSurf field (PC offset 16, u64) with
`struct.pack('>Q', …)` — i.e. byte-swapped. Evidence from the mp_raid GfxWorld materialMemory
region (352 inline materials paired PC↔genuine WiiU): genuine console keeps the PC memory
bytes **VERBATIM in 352/352 cases (0 match the u64-swap)** — same as the already-verbatim
contents field a few lines below. Fix: copy `pc[off+16:off+24]` verbatim; re-run the common_mp
matched-pair oracle (the previously-unexplained ~9/446 mismatches may be exactly this field).
COORDINATION: Track F's `gfxworld_regions.py` `conv_material_memory` currently applies a
downstream 8-byte patch compensating for this — after your fix lands + oracle passes, tell the
user so Track F removes its patch (their file, their edit). Do the fix EARLY in your session so
Track F isn't building more on top of the compensation.

## TRACK F INTEGRATION (main session, 2026-07-10 — Track F is COMPLETE, session retired)
Interface SIGNED OFF: `gfxworld_emit.emit_gfxworld(pc_zone_bytes, gw_offset, ctx) → (bytes,
fixups, log)`. Wire it into `assemble_zone` for the GfxWorld row. Notes:
- **CRITICAL: inject Track B substitute techset blobs into the emitted inline-material
  streams** (or re-point the ptr words) — Track F excludes inline techsets by design; the
  stream is NOT loadable without this. See `CAVEATS_gfxworld_trackF.md` §Integration.
- After your drawSurf verbatim fix + oracle pass, REMOVE Track F's compensating 8-byte patch
  in `gfxworld_regions.py::conv_material_memory` (ownership of all `gfxworld_*.py` transfers
  to YOU now that Track F is retired — you are the sole editor).
- GfxWorld's real allocation-event list for the interior pointer model (§3 above said
  "pending Track F"): derive it from the emit log/fixups now available, replacing the
  empirical skip constant where possible.
- Read `CAVEATS_gfxworld_trackF.md` fully — every synthesis/reencode class (BC3 lightmap
  reencode, KD streamInfo, PC-order sortedSurfIndex, PC-built cell aabb trees) is registered
  there for reading boot #1.
After integration: unresolved must go to ZERO (the 16,261 GfxWorld refs now have real
targets) → arm the full fatal assert → gate PASS → container authoring.

## Validation bars (unchanged)
≥2 maps for every new rule (raid + dockside pairs; skate blind for unresolved);
ST calibration must stay exact on all zones; keep docs truthful; never write under E:\.

## Standing after PASS
Track F GfxWorld (only missing emit row) → container authoring (real base into
`our_arr`) → pack/ipak/sig-patch (proven) → first boot.
