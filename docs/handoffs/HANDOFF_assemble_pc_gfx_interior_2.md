# HANDOFF — ASSEMBLE (B, pass 2): flip the interior model → unresolved→0 → GATE PASS

Continuation of `HANDOFF_assemble_pc_gfx_interior.md`. Pass 1 (ADDENDUM 8 of
`FINDINGS_runtime_interior_model.md` — read it first, it has the ordered list and all
measurements): skate blind re-verify PASS (constants blind-derived, fatal bar green, 32,413
unresolved all attributable); structural walkers BUILT and byte-exact (gfxworld_events.py,
material/FX events, xmodel_events rework with load-db TEMP classes; PC GfxStateBits=20B);
E-knobs measured blind-derivably on all 3 zones (E(gfx-planes): raid −83,360 / dock −67,744 /
skate −75,728; E(gfx-end) via GWMP plateau). Everything is behind `pc_structural_temps`
(default OFF); baseline guards all green.

## Work order (= ADDENDUM 8's list)
1. **Bake the E-knobs + re-derive every post-gfx constant under the flag.** Flipping
   invalidates all baked constants at once — re-derive as one operation, with the anchors
   suite (`raid_oracle_control.py anchors`) as the acceptance instrument after EVERY re-bake
   (absolute truth; the gate alone cancels shared bias). Frame-phase invariant applies:
   content anchors pin phases, never grids alone.
2. **Localize E@matmem** — the critical family: dpvs.surfaces→materialMemory ×5,281; every
   GfxSurface.material targets an inline matmem material, so this E must be exact.
3. **Region-pair the fine map** (emit fixups ×12,292 are disciplined — pair them through the
   Track F region list).
4. **conv_cells fixup audit.**
5. **Console-side interior model** (the 749,115 formula) — needed for the GENUINE-side
   resolver; per steer #4, a 2-map empirical constant is acceptable if the formula resists;
   blind-derivability is only required on the PC/skate side (already demonstrated).
Also in scope: smodelDrawInsts→slots ×4,668 (marked easy) and clipMap plane aliases ~13,185.

## ⚠ The pass-through class needs the typed-class discipline
"Data-noise needing verbatim pass-through rather than poison" — this project's history says
PC-value passthroughs masquerade as wrong pointers (why tagged poison exists). Any
pass-through class must be POSITIVELY proven non-pointer (fp_recompute-style predicate:
decode + alignment + target evidence, 2-map validated), never "unresolved and probably
data" — otherwise the fatal assert is hollowed out right before the build it protects.

## Guards (after every change, all must stay green)
`raid_oracle_control.py anchors` ALL PASS · `alloc_events.py` self-checks ·
`loader_sim.calibrate` ST exact · raid gate PASS / dockside 0 mod typed · skate blind
assemble fatal bar green with blind-derived constants.

## Definition of done — THE declaration
unresolved → 0 on raid AND skate (fatal armed, no untyped pass-throughs), both gates clean,
anchors green ⇒ **declare GATE PASS in PROJECT_STATE.md** ⇒ main session issues the
container-authoring go + releases the DLC session onto patch_zm. Standing: sole editor of
assemble/converter/gfxworld files; ≥2-map bar; never write under `E:\`; keep docs truthful.
