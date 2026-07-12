# HANDOFF — ASSEMBLE (B): PC GfxWorld interior virtual model → unresolved→0 → GATE PASS

The LAST item on the critical path. Both oracle gates are clean mod typed classes (raid PASS,
dockside 0 violations); the clipMap interior model is absolute-anchor-proven; the only thing
between here and the declared gate PASS is resolving the refs INTO the GfxWorld interior —
which needs the PC-side GfxWorld interior virtual model. Read first:
`FINDINGS_runtime_interior_model.md` (incl. ADDENDA 5–6 and the frame-phase invariant) and
the top entry of memory `trackG-runtime-interior-model`.

## Step 0 — skate blind re-verify (do before the inversion)
Re-run the skate blind assemble with **blind-derived constants** (the material-name sweep is
now unambiguous → skate's clipMap constants derive from its own PC zone). This rehearses the
property that matters at boot: everything derivable from PC alone. Any surprise here surfaces
now, cheaply.

## The problem
unresolved = 24,671 raid / ~19,926 dockside / (skate similar), almost all refs into the
GfxWorld interior. Resolving them needs: which PC GfxWorld regions consume no virtual space
(the measured PC deficit ≈ 10,297,331; image-class regions = 10,234,048; residual 63,283
unexplained) and each region's PC runtime base.

## Steers (standing, from prior passes — don't re-litigate)
1. **Our-stream side is fully known**: Track F's `emit_gfxworld` fixups/log are the exact
   region list with methods — the inversion is PC-side only.
2. **63,283 first**: before hunting new classes, test the OAT ZoneCode DPVS/RUNTIME_VIRTUAL
   family (cellCasterBits, sceneDynModel/Brush, shadow-vis, sceneEntCellBits, visData,
   surfaceMaterials, dynEnt bits — ≈338 KB total on raid counts) for a subset landing on
   63,283, and check PC block-1 residency (header 516,928). Known: console's runtime majority
   is GX2-side allocation OUTSIDE OAT's model — do not expect OAT to explain the console
   number; the PC number is the one you need.
3. **Anchor toolkit generalizes**: the field-lookup semantics + offset-pointer grids that
   cracked the clipMap interior are the instruments for the GfxWorld inversion; dense
   families (plane pointers 16,733; SndBank anchors) exist on both oracle maps.
4. **Bars**: raid+dockside = anchor verification (absolute, not just gate-relative — run
   `raid_oracle_control.py anchors` after every model change); skate = blind-derivability
   (internal anchor collapse + fatal assert). **2-map-validated empirical per-zone constants
   ARE an acceptable model** if the structural inversion resists — the boot question is
   whether skate's constant derives blind, not whether it is explained.
5. **Frame-phase invariant**: never re-bake a frame constant from grids alone; content
   anchors or a gen-match family pin the phase.

## Regression guards (run after every change — all must stay green)
`raid_oracle_control.py anchors` (ALL PASS baseline) · `alloc_events.py` self-checks
(xmodel 440/440, 491/491) · `loader_sim.calibrate` ST (7009/6, transit 2821/0) · both
oracle gates (raid PASS / dockside 0 mod typed).

## Definition of done — THE declaration
unresolved → **0** on raid AND skate (fatal assert armed), both gates clean, anchors green.
Then **declare GATE PASS in PROJECT_STATE.md**. That declaration triggers the main session's
container-authoring go and releases the DLC session onto patch_zm. Standing constraints:
sole editor of assemble/converter/gfxworld files; ≥2-map bar for new rules; never write
under `E:\`; keep PROJECT_STATE/CAVEATS/memory truthful.
