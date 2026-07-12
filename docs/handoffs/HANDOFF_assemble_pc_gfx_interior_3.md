# HANDOFF — ASSEMBLE (B, pass 3): close unres:techset-interior → unresolved 0 → GATE PASS declaration

> ✅ **DONE (main session, 2026-07-10).** See `FINDINGS_runtime_interior_model.md`
> ADDENDUM 10. unresolved = 0 raid + skate (raid gate PASS, skate blind fatal bar
> green), dock 3 mod the known CAVEATS §16 caveat. GATE PASS declared in
> PROJECT_STATE.md. Resolution: per-field decomposition (diag_ts_interior/
> _fields/_solve.py) → ts-dangle in-bounds mirror (pointer families) +
> ts-noise-verbatim (clipMap/ComWorld/Glasses data words); both re-source
> dispositions measured impossible (content absent from our stream AND the
> genuine zone — genuine dangles equivalently).

Continuation of `HANDOFF_assemble_pc_gfx_interior_2.md`. Pass 2 (ADDENDUM 9 of
`FINDINGS_runtime_interior_model.md` — read it first) executed the whole ADDENDUM 8
list: `pc_structural_gfx` flipped (split from the full temps flag — the XModel/FX/
Material interior flip is deferred, it disturbs XModel-interior alias emits),
E@matmem solved (matmem ARRAY field dedups, stride 8, one blind constant/zone),
region-paired fine map live (blanket gfx tags gone from Omap.reloc), conv_cells
audit clean 2-map, and the CONSOLE-side model solved — **749,115 = runtime-virtual
allocated before dpvsPlanes.planes** (`gfxworld_console_events` + knobs under
`co_structural_gfx`; raid 750,191/234,650/919,836, dock 472,088/—/565,044 in
events-model frame).

**State:** raid gate PASS · dockside 0 mod typed (2 CAVEATS §16 corpus techsets) ·
anchors ALL PASS · ST 7009/6 · self-checks green · skate blind fatal-bar green with
fully blind constants (`loader_sim.derive_pc_policy`, now incl. E_mm).
**unresolved: raid 336 / dock 527 / skate 295 — ALL `unres:techset-interior`.**

## The one remaining class (measured decomposition, raid: 168 unique targets)
- 99 pshader + 45 vshader regions: PC linker CONTENT-dedups (strings + 16 B
  constants) against bytes embedded in DXBC bytecode. Unreproducible byte-wise
  vs our GX2 blobs.
- 19 args rows, 4 tech-hdr, 1 tech-name.
- Sources: XModel materialHandles (309) / surface headers (251) / inline materials
  in XModel+FX (convert_material), a few GWMP/finalize.
Per-field semantics are the missing piece: identify WHICH material/surface fields
these are, give each family a positive predicate (fp_recompute-style: field type +
target-region evidence, 2-map validated), then either re-source (strings — suffix
re-sourcing already exists and is class-verified by the gate), resolve
structurally, or pass through verbatim as proven data.

⚠ A blind 16-byte endian-swapped binary re-source was tried and REVERTED: without
a structural predicate it hijacked ComWorld float/stale words — exactly the
hollow-pass-through failure mode. Do not reintroduce it without the per-family
predicate.

### Main-session clarification: three dispositions, decided per-field
Our emitted zone contains NO PC shader bytecode — techsets ship as substituted
genuine console (GX2) blobs per Track B. So the PC linker's dedup targets inside
DXBC regions have no byte-equal counterpart at the corresponding location in our
stream, and each referencing field has exactly one of three legitimate
dispositions; the predicate must positively decide which:
1. **Data noise misread as a pointer** (fp_recompute-style) — prove it per-field
   and type it as data.
2. **Real pointer whose PC value content-dedup'd into shader bytes by
   coincidence** — correct target is wherever that content lives in OUR zone:
   content-lookup re-source, per-field, under the 2-map bar.
3. **Real pointer into shader content that genuinely doesn't exist in our zone**
   — a substitution-model gap; must surface as a named violation, never get
   classed away.
A blind re-source cannot distinguish these — that is exactly how it hijacked
ComWorld. Per-field, positively, with both oracles.

## Also open / notes
- `_GFX_REG_OURS` gate table reads the single `_GFX_PAIR_CACHE` entry — valid only
  one-zone-per-process (true for raid_oracle_control CLI runs); harden if the gate
  ever runs two zones in one process.
- OUR-side boot policy (`our_policy` in assemble pass 3) is still None: the console
  structural knobs for OUR emitted zone (skate: predict planes-band from PC-known
  counts, or derive from our own emitted zone via the blind console recipes) is
  container-authoring scope — raid/dock values can seed the formula hunt
  (749,115 vs 471,012; +1,076 events frame).
- Full `pc_structural_temps` (XModel/FX/Material interiors) remains opt-in — its
  own interior event model is the mechanism gating the XModel drift-band families.

## Guards (after every change, all must stay green)
`raid_oracle_control.py anchors` ALL PASS · `alloc_events.py` + `gfxworld_events.py`
self-checks · `loader_sim.py` ST exact · raid gate PASS / dockside 0 mod typed ·
skate blind assemble fatal bar green with `derive_pc_policy` constants.

## Definition of done — unchanged
unresolved → 0 on raid AND skate (fatal armed, no untyped pass-throughs), both
gates clean, anchors green ⇒ declare GATE PASS in PROJECT_STATE.md ⇒ main session
issues the container-authoring go + releases the DLC session onto patch_zm.
Standing: sole editor of assemble/converter/gfxworld files; ≥2-map bar; never
write under `E:\`; keep docs truthful.
