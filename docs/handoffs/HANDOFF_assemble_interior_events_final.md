# HANDOFF — ASSEMBLE: XModel/FX/techset interior event model → unresolved→0 → gate PASS

Continuation after the 2026-07-10 dissolution session (DD = stale-str class, XAnim =
source recompile, DPVS-mirror falsified — console GfxWorld runtime majority is GX2-side,
outside OAT's model; empirical 2-map constants REMAIN the working GfxWorld model). Read
`FINDINGS_runtime_interior_model.md` for the measurements. **One mechanism remains** and
this handoff closes it.

## The single named fix
Everything left is the **XModel/FX/techset interior allocation-event model** on both sims:
- last gate ptrbads: raid 293 + dockside 221 + dockside DD ×1 + GWMP ×1/map — all
  string/name dedups resolving through the interior drift band;
- the PC pre-GfxWorld deficit (105,045);
- the GfxWorld guard-margin hack;
- and (with the GfxWorld interior) unresolved→0.

## The recipe is proven — apply it a third time
This is the SAME fix that closed clipMap and GWMP: adapt the existing per-type walkers to
emit ordered allocation-event lists (rel_off, size, align, string allocs incl. their
alignment behavior) and replay them in loader_sim instead of verbatim register-once.
- **XModel**: `xmodel_pc` / `xmodel_convert` walks already visit every allocation (bones,
  strings, surfaces, collmaps chain) — emit events. The ST calibration bounded this drift as
  small per-asset but there are 440 models; small × 440 = the 105 K deficit class.
- **Techsets**: the corpus blobs are console-verbatim, but their interior string/struct
  allocs still consume aligned runtime — walk the blob with the techset layout (Track B's
  selfcheck walker exists) and emit events. 224–245 per zone.
- **FX**: fx_convert's span logic knows the elem/visuals/string layout — emit events.
Because PC and console serialize these types with identical layout, ONE relative event list
per asset serves both sims (the clipMap/GWMP precedent).

## Order & verification
1. XModel events first (largest population; the ST calibration is your regression guard —
   it must stay exact at every step: raid 7009, dockside 10,787→569,444).
2. Techsets, then FX.
3. After each type lands: re-run BOTH gates; the drift-band residuals should shrink
   monotonically. Expected end state: raid 0 violations (mod typed classes), dockside 0,
   GWMP ×1 and the DD string-like ×1 collapse with the band.
4. Remove the GfxWorld guard-margin hack once the pre-GfxWorld deficit closes — the guard
   should become exact, not padded.
5. **GfxWorld interior for skate (blind)**: our-stream side is fully known (Track F emit
   fixups/log = the real region list); the PC-side inversion must be derived from the PC
   zone itself — `derive_gen_policy` + skate's own anchor families (SndBank-style; GWMP tree
   if present). No oracle exists for skate: the bar is internal consistency (anchors
   collapse to one constant, as raid/dockside did) + the fatal assert.
6. **unresolved → 0 on raid AND skate, fatal armed → declare gate PASS in
   PROJECT_STATE.md.** That declaration triggers container authoring + the DLC patch_zm go.

## Also fold in (small, from the last session's findings)
- CAVEATS: add the loader-tolerance note if absent — genuine retail zones ship dangling
  string pointers (DD sound/notify members into vertex data), so dangling-on-absent-string
  is a shipped, loader-tolerated class; recalibrate boot-risk reading accordingly.
- The anim-recompile gate rule (difflib-verified small gen-side insertions) and stale-str
  class are in — keep them typed, don't widen them silently.

## Standing
Sole editor of assemble/converter/gfxworld files. ≥2-map bar for every new rule; ST
calibration exact after every change; skate blind bar = internal consistency + fatal.
Never write under `E:\`. Keep PROJECT_STATE/CAVEATS/memory truthful — including declaring
PASS the moment it is true and not before.

## Definition of done
Interior events live for XModel/techset/FX on both sims; drift-band residuals gone from
both gates; guard hack removed; skate assembles with unresolved=0 under the fatal assert;
**gate PASS declared**. The linker is then ready: container authoring is the next handoff,
and the main session releases the DLC session's patch_zm build.
