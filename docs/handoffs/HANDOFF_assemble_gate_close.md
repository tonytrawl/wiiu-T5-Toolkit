# HANDOFF — ASSEMBLE session: integrate CHASE bundle + close residuals → gate PASS

SUPERSEDES `HANDOFF_assemble_integrate_chase.md` (written before the loader-sim session
finished — its sequencing is stale, its substance is folded in here). Context docs:
`FINDINGS_loader_sim_pointer_model.md` (pointer model — DONE, calibrated on 4 console + 5 PC
zones) and `FINDINGS_chase_content_gaps.md` (all four content gaps resolved; validated
raid+dockside). Both sessions independently found the SAME genuine-side clipMap walk gap —
chase's fix spec resolves the item you quarantined; nothing goes back to chase (that session
is retired).

## State you inherit
Three-pass assemble with runtime-correct pointers; fatal unresolved assert armed; insert-set
fact corrected (aliased MAP_ENTS row @1 raw-48, raw-47=GLASSES, + extra FOLLOW SOUND; no
MAP_ENTS body to synthesize). Gate: StringTable/KVP/FxImpactTable pointer-equivalent; assets
853–882 quarantined pending item 1.

## 1. Fix the gate's clipMap extent (the quarantine lifter)
Dispatch clipMap_t extent in `raid_oracle_control` to `clipmap_probe.walk` (console '>', same
`_SIZES` — spec in FINDINGS_chase_content_gaps §3). This un-quarantines 853–882 and replaces
the truncation-artifact baseline. Re-run and RE-BASELINE the gate; prior tail verdicts
(XAnimParts/RawFile/SndBank "violations") were already shown to be artifacts of this gap.

## 2. Integrate the chase converters (both byte-exact-validated on 2 maps)
- **GameWorldMp**: our 241,860 emit is a pc_to_console struct_layout mis-width (u16-swap of a
  u32, under-consume). Port `probe_gameworldmp_convert.py` (byte-exact mod alias words, raid
  308,076 + dockside). No stub — pathfinding converts exactly.
- **GSC**: dispatch ScriptParseTree bodies through `gsc_swap.convert_spt_body` (13/13 raid +
  17/17 dockside byte-exact).

## 3. Allowlist classes + pairing rule (gate config)
- clipMap: 166 float-mantissa-drift words (staticModelList/cmodels).
- DestructibleDef: float-LSB (word delta == 1). Do NOT allowlist its pointer diffs — see 4.
- Glasses −32: two −16 textureTable rows in nested inline materials — extend the material
  class to nested.
- no-console-pair ×2: pair to console-aliased twins per chase's specced rule.

## 4. Close the two named pointer residuals
- **destructible→XModel geometry-share class (~220 ptrs)**: pieces alias the source XModel's
  geometry. Build the destructible/xmodel share map so these encode the shared target
  (documented in FINDINGS_loader_sim §violations). Bounded; genuine raid is the oracle.
- **mp_skate 573 'outside' unresolved**: classify every one. Expected buckets: more
  geometry-share, suffix-dedup collisions (benign, documented class), or real emit gaps.
  Bar: each of the 573 attributed to a named class; anything unexplained is a bug —
  unresolved must end as GfxWorld-only (tagged) on BOTH maps.

## 5. Declare the gate verdict
After 1–4: raid gate must show only allowlisted classes with semantically-correct pointers.
Record the PASS (or the named exceptions) in PROJECT_STATE.md. Note the standing caveat from
the findings doc — the linear-interior approximation inside verbatim-walked types — in
CAVEATS_nobackbone_boot.md if not already there.

## Out of scope / standing
Track F owns `gfxworld_*.py` (still the only missing emit row). Container authoring
(real base fed into our_arr) + pack/ipak/sig-patch come after the gate PASS — already-proven
machinery. Never write under `E:\`; ≥2-map validation for any new rule; keep docs truthful.

## Definition of done
Gate PASS on re-baselined raid (only allowlisted classes); unresolved = GfxWorld-only on raid
AND mp_skate (573 fully attributed); chase converters integrated byte-exact; docs updated.
Remaining path then: Track F GfxWorld → container → pack → first boot.
