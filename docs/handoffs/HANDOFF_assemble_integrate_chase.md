# ⛔ SUPERSEDED by `HANDOFF_assemble_gate_close.md` (2026-07-09) — do not work from this doc.
# Written before the loader-sim session finished; its sequencing is stale.

# ADDENDUM — ASSEMBLE session: integrate the CHASE bundle (do BEFORE trusting gate re-runs)

Companion to `HANDOFF_assemble_loader_sim.md`. The CHASE session resolved all four content-gap
tasks (`FINDINGS_chase_content_gaps.md` — read it; all claims validated on raid + dockside).
Headline: **none of the gaps was real console divergence** — they were our converter/walker
bugs plus allowlist classes. Integrate in this order; item 1 changes what your gate reports.

## 1. FIX THE GATE FIRST — clipMap span truncation (invalidates prior tail results)
`raid_oracle_control`'s console span walk truncates clipMap_t ~2.17 MB early → **every span
after asset 852 (raid 853–888) is garbage**; the zone's last 15.6 MB of real tail bodies was
never reached. Fix per the spec: dispatch clipMap_t extent to `clipmap_probe.walk` (console
'>', same `_SIZES`). Then RE-RUN the gate and re-baseline: the previous
`exact=105 / violation=38` numbers are partially artifacts. Do this before drawing any
conclusion from loader-sim re-runs — otherwise you calibrate against a broken ruler.

## 2. GameWorldMp — apply the mis-width fix (it's OUR bug, in your files)
PC and console serialize GameWorldMp identically (nodes stride 144, pathlink stride 16;
T6_Assets.h's 12-byte pathlink is wrong). Our 241,860 emit came from pc_to_console
struct_layout mis-width (u16-swapping a u32 and under-consuming).
`probe_gameworldmp_convert.py` is the executable spec — byte-exact mod alias-pointer words on
raid AND dockside. Port it into your converter path; no stub needed, pathfinding converts
exactly.

## 3. Wire the GSC swapper
`gsc_swap.convert_spt_body` (wraps the verified opcode transcoder in `wiiu_ref/gsc_diff.py`).
Dispatch ScriptParseTree bodies through it. Bar already met: 13/13 raid + 17/17 dockside
byte-exact.

## 4. New allowlist classes + rules (gate config)
- clipMap: 166 float-mantissa-drift words in staticModelList/cmodels (source divergence).
- DestructibleDef: float-LSB class (word delta == 1); DD7's unaligned b5 aliases are POINTER
  class — expect the loader-sim pass to fix them, don't allowlist as content.
- Glasses −32: exactly two −16 textureTable rows in nested inline materials — extend the
  existing material class to nested materials.
- no-console-pair ×2: pair to their console-aliased twins per the specced pairing rule.

## Order of operations with the loader-sim work
Gate fix (item 1) → converter integrations (2, 3) → allowlist update (4) → clean gate
baseline → THEN judge the loader-sim pass against that baseline. Everything else in
`HANDOFF_assemble_loader_sim.md` stands, including the ≥2-map simulator calibration and the
MP-insert-set verification (note: CHASE confirmed type-47 body = Glasses on raid — fold that
into your insert-set answer).
