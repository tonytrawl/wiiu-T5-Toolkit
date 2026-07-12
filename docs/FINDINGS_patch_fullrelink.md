# FINDINGS — full unlink→relink (Path A) : the interior-pointer hypothesis is DISPROVEN

2026-07-11. Side project (isolated). Base linker untouched. All new code in
`dlc loading/native/fullrelink/`. Companion to `HANDOFF_patch_fullrelink_sideproject.md`.

## What Path A set out to test
HANDOFF §4 leading hypothesis for the additive-shift crash (`fx_pistol_shell` OSFatal):
*"a VERBATIM asset holds an alias pointer into a shared-data INTERIOR that the conservative
omap relink MISSES → stale after the +delta tail shift."* Path A = give the probes a mode that
yields exact pointer-field offsets, then threshold-relink precisely those (false-positive-free
`_editT`).

## Method (no base edits)
`fullrelink/diag_interior_ptrs.py`: monkeypatch the module-level `u32` of the 4 instrumentable
probes (`xmodel_probe`, `shader_probe`, `fx_probe`, `gfximage_probe` — cover XModel and its inline
Material/MaterialTechniqueSet/GfxImage) to RECORD every offset whose read value is an alias
(0xA0000001..0xBFFFFFFF). Also wrap `Cur.cstr` to record interior inline-string starts. Run each
verbatim asset through its delimiter, harvest true pointer offsets, classify each alias target vs a
COMPLETE registered-offset set from a full base ReEmitter pass. Plus a probe-independent whole-zone
cross-check (every asset type incl. the closure-probe ones).

## Results (upd_patch_mp.ff, 14.7 MB, 1533 assets; shift_from block5=8556214)
- Base pass completes to EOF; registered block-5 offsets = 75,538 (trustworthy/complete).
- Alias words harvested from verbatim bodies: techset 7770, Material 991, XModel 135, FX 108 — and
  **every one is "omap-missed."** That is the tell: they are NOT pointers.
- Of 9004 omap-missed aliases, 927 have target ≥ shift_from. **0 of them target a harvested
  interior inline-string.** The dominant target (`11210816`, hit by dozens of unrelated techsets)
  points to a **zero region**; others (`10285640`, `10078996`, …) are binary GX2 register data.
- shader_probe itself documents these (lines 168–171): GX2 register-table slots "often hold stale
  non-zero words with count 0 — loader ignores them." Those stale words ARE the false positives.
- Probe-independent whole-zone scan for aliases targeting ANY inline-string start (unregistered,
  ≥ shift_from), across ALL asset types incl. XAnimParts/SndBank/DDL/GfxWorld/MenuList: only **12
  hits total, all garbage coincidences** (e.g. one DDL with many words all pointing to the SAME
  binary offset 9770916; targets contain binary, not names).

## Conclusion
**There are essentially NO genuine missed interior name-alias pointers in verbatim assets anywhere
in the zone.** The 927 "stale" words are GPU/GX2 register garbage the loader ignores. Therefore:
1. HANDOFF §4's leading hypothesis (missed interior-string alias) is **disproven by measurement**.
2. The current `remap_ptr_omap` verbatim relink is **already correct/complete for genuine pointers**
   — it correctly leaves the garbage alone.
3. This is exactly why `_editT` (blind threshold on verbatim bytes) crashes EARLIER: it rewrites the
   ignored GX2 register garbage → GPU data corruption. Same 927-class words, 88,509 total blind FPs.
4. **Path A cannot fix the crash — there is no missed pointer to fix.** The `fx_pistol_shell` asset
   is byte-identical and pointer-free; the loader fails purely on POSITION. This is the genuine Wii U
   loader position-dependency HANDOFF §4 named as the fallback, and it is NOT addressable from file
   bytes. **Next step is GUEST-DEBUG** (Cemu breakpoint at the OSFatal asset-resolution site, or
   delta-bisect the shift threshold), not better relinking.

Residual caveat: the scan tests aliases to string boundaries and to registered sub-regions. A
genuine alias into a NON-string, NON-registered interior of a verbatim asset would be value-
indistinguishable from GX2 garbage — but (a) structural StringTable cells that alias asset interiors
already go through the THRESHOLD path (`remap_ptr`, fix #3), not omap, and (b) the pointer-free
byte-identical nature of the crash asset + `_editT` crashing earlier both argue against any
un-relinked pointer being the cause.

## PIPELINE report-back
- PIPELINE: Console techset/Material bodies carry GX2 register-table slots holding **stale alias-
  range garbage words with count 0 that the loader ignores**. Any pointer-relink that scans by VALUE
  (not by struct-field role) will corrupt these → render/boot faults. The pipeline's pointer emit
  must only touch struct-defined pointer fields, never value-scan GX2 register blocks.
- PIPELINE: `emit_verbatim` registers only an asset's START, not its interior inline strings — but
  measurement shows no genuine cross-asset alias depends on those interiors here, so completing the
  registry is NOT required for the mapsTable relink (was the presumed fix; it is not).

## Artifacts
- `dlc loading/native/fullrelink/diag_interior_ptrs.py` — the diagnostic (re-runnable).
- Run: from `native_linker/`,
  `python "../dlc loading/native/fullrelink/diag_interior_ptrs.py" "../dlc loading/native/upd_patch_mp.ff" --tag mp`
