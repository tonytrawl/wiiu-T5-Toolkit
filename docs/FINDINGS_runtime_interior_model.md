# FINDINGS — Runtime-allocation + interior-alignment model (Track G) — 2026-07-10

## ADDENDUM 10 (2026-07-10, main session): unres:techset-interior CLOSED — raid PASS/0, skate blind 0, dock 3 mod known caveat

Per-field decomposition (diag_ts_interior.py / diag_ts_fields.py / diag_ts_solve.py,
new): raid's 336 tagged fixups are **real pointer fields** — XModel materialHandles
(103), inline-material texdefs (88), surf-hdr verts/tris ptrs (+12/+32/+40), XModel
body bone-array ptrs (+8/+24/+28), FX/Material texdefs, 1 GfxWorld emit fixup —
whose PC values the PC linker dedup'd into DXBC shader bytes.

**Both re-source dispositions were tested and are IMPOSSIBLE, measured:**
- A zone-wide "shader progs are PC-temp" inversion model over-corrects by MBs and
  scatters targets to nonsense (diag_ts_solve) — progs DO consume PC runtime;
  falsified.
- Content-lookup: the dedup'd PC content exists in NEITHER our emitted stream NOR
  the genuine console raid zone (146/150 unique targets absent; 4 hits are
  low-entropy). Genuine consoles ship these fields DANGLING into GX2/shader bytes
  and run — link-time heap-reuse/content accidents on BOTH linkers.

**Dispositions shipped (produce_nobackbone ts-span branch, ordered):**
1. String re-source (existing, unchanged; raid 17 / dock 19 / skate 48).
2. **ts-dangle** typed class: source root ∈ {XModel, FxEffectDef, Material,
   GfxWorld} (the measured pointer families) AND substituted blob present →
   emit the boot-safe in-bounds mirror: same techset, same interior delta
   clamped into OUR substitute blob (`Omap.ts_co/ts_olen`). Genuine ships small
   in-block dangles; the old poison tag was a ~0.5 GB out-of-block offset.
   raid 336 / dock 441 / skate 276.
3. **ts-noise-verbatim** typed class: source root ∈ {clipMap_t, ComWorld,
   Glasses} — measured DATA words (clipMap recomputed-float family dock x74;
   ComWorld float noise + stale defName dedups skate x19/dock x8; Glasses x1).
   Verbatim preserves the genuine float content the poison used to corrupt.
4. Anything else still TAGS (a new family must be measured before it may
   dangle) — on dock that is exactly the 2 Material refs into the CAVEATS §16
   missing-blob techsets (surfaced with the MISSING violations) + 1
   unres:GfxWorld word (pending class).

**Gate:** semantic_diff's TECHNIQUE_SET×TECHNIQUE_SET branch extended — 16-B
content-equal still proves ok; unequal-content interior pairs are now classed
ts-dangle (replaces the former (#tagged, TECHNIQUE_SET-interior) allowlist,
same coverage). The 7 string-suffix targets ('olA', 'lightHeroScale', …) are
XModel/FX data noise (no such string fields exist there) and correctly stay in
class 2/3 — our GX2 blobs don't embed DXBC arg names.

**End state:** raid gate PASS, **unresolved 0**; skate blind assemble
**unresolved 0** (fatal bar green, fully blind constants); dockside unresolved
85 → 3 = 2 known-caveat techset refs + 1 GfxWorld-pending; anchors ALL PASS;
alloc_events / gfxworld_events / loader_sim ST self-checks green. Trace hook:
`produce_nobackbone.TS_TRACE` + `Omap.ts_trace` (final-pass techset-interior
trace, used by the diag scripts).

## ADDENDUM 9 (2026-07-10, part B session 2): interior model FLIPPED — unres:GfxWorld = 0 on ALL zones, raid gate PASS, dock 0-mod-typed, 749,115 SOLVED
Executed ADDENDUM 8's ordered list end-to-end. **unresolved: raid 24,671 → 336,
dock 19,926 → 527, skate 32,413 → 295 — unres:GfxWorld = 0 everywhere**; the
whole remainder is ONE class (unres:techset-interior, decomposed below).

**1. Flag flipped as `pc_structural_gfx` (SPLIT from pc_structural_temps).**
The full flag's XModel/FX/Material structural temps disturb alias emits into
XModel interiors (dockside clipMap cStaticModel family: 98 ptrbad; raid same
words go unresolved) — the GfxWorld-only subset is what items 1–3 need, so it
shipped alone; the XModel interior flip stays opt-in until its event model is
right. Knobs (all blind, ADDENDUM 8 recipes): A = pre_skip_pc['GfxWorld'] from
the clipMap-hdr planes alias (raid −104,032 = the known pre-gfx drift; dock
−107,584; skate −71,808); B = gfx_residual_pc = E@end − E@planes via GWMP
plateau tie-high (raid −64,320 / dock −88,848 / skate −113,560). Post-gfx
constants re-derived under the flag: **S_clip UNCHANGED** (−440/−644/−552 —
the knobs anchor the same absolute rt at gfx end); PC lump −2,172/−84/−268.
Whole recipe promoted to **`loader_sim.derive_pc_policy(pc_path)`** (blind,
reproduces every baked constant on raid+dock).

**2. E@matmem SOLVED — it's the ARRAY, not the inline materials.** The
dpvs.surfaces material aliases are AddPointerLookup FIELD dedups targeting
`materialMemory[k].material` — on all 3 zones every entry is referenced at
exact stride 8 (raid 352/352, dock 390/390, skate 733/733). One blind constant
per zone (`gfx_matmem_pc`: min distinct alias − model rt of the array; raid
3,144 / dock 3,628 / skate 2,312), applied as a skip before the region with
the end total unchanged. Family exact: 5,281/5,281 raid + 4,860/4,860 dock.
(Side finding: PC inline matmem materials walk end-to-end with
`material_events` — 352/352 raid, whole region end-exact.)

**3. Region-paired fine map LIVE.** `gfxworld_emit.region_pairs(pc, off, log)`
pairs the emit log's console regions with PC marked spans (raid: 25/32
same-size incl. planes 139,160 and cells 186,035 byte-equal; co-end == emit
len). produce_nobackbone registers them as fine entries (same-size → linear
exact; size-changing → start-only; materialMemory → array prefix), and
Omap.reloc's blanket gfx tags are GONE: gfx-interior targets resolve ONLY
through scaled/fine (miss stays tagged — no approximation inside gfx). The
below-start guard window is kept.

**4. conv_cells audit CLEAN (2-map):** all cells fixups resolve INTO the cells
region itself (raid 2,307/2,307, dock 1,693/1,693 — self-referential aabb
trees; noise would scatter across the 21 MB span). No over-listed data words.

**5. CONSOLE-side interior model SOLVED — 749,115 is the planes band.**
Measured from the genuine zones' own anchors under a linear model:
raid E@planes = **749,115 exactly** (pure runtime-virtual BEFORE
dpvsPlanes.planes — GX2/DPVS allocs, no file bytes; images play no role, the
E profile is runtime extras, not temps), E@matmem 983,765, E@end 919,776;
dock E@planes 471,012, E@end 564,984 (dock has **NO inline matmem
materials** — 0 name strings in its console gfx; no matmem band).
Implemented as `gfxworld_events.gfxworld_console_events` (G2 wiiu region walk
+ knob skips at planes/matmem/end) wired into `loader_sim.simulate` under
`co_structural_gfx`. Constants re-measured UNDER the events model (the old
generic walk carried 60 B of align pads inside gfx): raid planes_skip
750,191 / matmem_skip 234,650 / gfx_skip 919,836; dock 472,088 / — / 565,044.
The +60 end totals keep post-gfx rt (and every baked post-gfx constant)
bit-identical. Genuine allocation-start hits rose 8,744 → 10,148 (independent
truth signal). SSkinShaders/dock-tail walk shortfall = one linear trailing seg.

**6. Gate upgrades (typed, positive-evidence):**
- REGION-relative GFXWORLD compare (`_gfx_region_at` + tables from
  region_pairs/co_regions): registered-SYNTH size drift (our raid streamInfo
  −8,912, dock −24,124) shifts downstream deltas; a pointer is correct iff
  both sides land at the same offset of the SAME region.
- fp_recompute same-asset exception for GFXWORLD when the two interior deltas
  disagree > 64 KB (GFXWORLD spans most of rt space, so float noise lands in
  it on both sides; the dock (16,12) real family, delta 16, stays excluded).
- TECHNIQUE_SET×TECHNIQUE_SET 16-byte content-equality class (2^-128
  accident bound).
- ComWorld joined the stale-str class (primary-light defName dedups whose
  GENUINE copy dangles into recomputed GX2 bytecode; ours re-sources the
  real string).
- Omap string re-sourcing now accepts SUFFIX dedups (`'…postFxControlA' →
  'olA'` — the PC linker dedups string tails; leading-NUL search first).

**End state:** raid gate **PASS**, dockside **0 mod typed** (only the 2
CAVEATS §16 corpus techsets), anchors ALL PASS, ST 7009/6 exact,
alloc_events + gfxworld_events self-checks green, skate blind assemble 835
assets / fatal bar green with fully blind constants (incl. E_mm).

**REMAINING for unresolved→0 (the one open class, measured on raid):**
`unres:techset-interior` ≈ 300/zone (raid 336, dock 527, skate 295). 168
unique targets: **99 pshader + 45 vshader regions** (PC linker content-dedups
against bytes EMBEDDED IN DXBC bytecode — strings and 16 B constants;
unreproducible byte-wise against our GX2 blobs), 19 args, 4 tech-hdr, 1
tech-name. Sources: XModel materialHandles/surface headers + inline materials
in XModel/FX. A blind 16-byte endian-swapped re-source was tried and
**REVERTED** — without a structural predicate it hijacks float-noise words
(the hollow-pass-through failure mode the handoff warns about). Each family
needs a positive predicate (per-field semantics + target-region evidence,
2-map) before it may resolve or pass through. NOTE: `_GFX_REG_OURS` uses the
single _GFX_PAIR_CACHE entry — valid for one-zone-per-process gate runs only.

## ADDENDUM 8 (2026-07-10, part B session 1): PC GfxWorld interior model — Step 0 PASS, structural walkers BUILT, E measured on 3 zones, NOT yet wired
**Step 0 (skate blind re-verify): PASS.** Blind derivation works end-to-end on
skate's own PC zone: SndBank family seeds the window → material-name sweep
gives a UNIQUE perfect peak 234/234 at S_clip = −15,528,632 → internal anchors
exact (verts grid 6,827/6,827 mod-0; preset field anchors 12/12 on
owner_def+56, owners #209/#250) → full blind assemble: 835 assets, fatal bar
green, all 32,413 unresolved attributable (GfxWorld 32,078 + techset 335).
Blind skate clipMap policy: pre_skip_pc −15,528,632, lump −252.

**Built + validated (byte-exact end offsets):**
- `gfxworld_events.py` (NEW): PC GfxWorld per-region events via a READ-ONLY
  mark-hook on gfxworld_probe2; image regions (probes/lightmaps/outdoor) =
  TEMP; `interior_residual` knob. Walks raid/dock/skate end-exact
  (raid temps 10,234,048 = the known image-class sum).
- `alloc_events.material_events_pc` / `fx_events` / `material_events` (NEW)
  + `xmodel_events` reworked: structural TEMP classes per the T6 load db —
  inline Material roots (112), inline GfxImage whole bodies (pc_image_span),
  PhysPreset roots (84), FX root (76), XModel root (248); segs PACKED
  (align 1; part-A-proven). PC GfxStateBits = **20 B** (console 8) — found by
  a −24/material sub-span proof. 606/606 raid pre-gfx assets walk byte-exact.
- Wired into `simulate_pc` behind **policy flag `pc_structural_temps`
  (default OFF — tree stays green)** + `gfx_residual_pc` knob.

**Measurements (structural-temps model, no other constants):**
- E(gfx planes) via the clipMap-hdr planes alias (blind-derivable absolute
  anchor): raid −83,360 / dock −67,744 / skate −75,728 ⇒ true pre-gfx
  non-virtual raid = 104,030 (walker temps 187,390 overshoot; NO subset of
  {mat_root 73,360, img_hdr 59,712, img_name 933, img_ldef 11,196, img_pix
  40,257, phys 1,932, fx_root 12,008} hits it ⇒ per-class composition is
  heterogeneous — open).
- E(gfx end) via GWMP tree anchors (plateau ±16): raid +19,040 / dock −21,104
  / skate −37,832 ⇒ gfx-INTERIOR extra non-virtual ≈ raid 102,400 / dock
  46,640 / skate 37,896 (≈ raid matmem inline-material roots 39,424 + the old
  63,283 residual — composition open).
- **Both anchor families are blind-derivable from the PC zone alone** ⇒ the
  two knobs (pre-gfx residual, gfx_residual_pc) derive per-zone without an
  oracle even if the composition stays unexplained (steer #4).

**unres:GfxWorld decomposition (raid, measured):** emit fixups = only 12,292,
disciplined: dpvs.surfaces→materialMemory ×5,281 (every GfxSurface.material →
an inline matmem material — E@matmem must be exact), smodelDrawInsts→slots
×4,668 (XModel handles), cells→cells/planes ×2,307 (real, but conv_cells may
over-list portal float DATA words — audit before reloc'ing), models 33,
body 3. The rest of the ~24,322 tags = clipMap plane aliases into gfx planes
(~13,185, real) + data-noise words from other assets landing in the gfx rt
span (need verbatim pass-through, not poison).

**Remaining for unresolved→0 (ordered):** (1) derive+bake the two PC knobs
per zone + re-derive ALL post-gfx constants under the new model (flip the
flag default only when anchors suite + both gates + ST are green under it);
(2) matmem-exact placement (the 5,281 surfaces family) — needs the gfx
interior extra LOCALIZED (matmem structural 39,424 + unknown ~63K); (3)
region-pair the omap fine map PC↔Track-F-emit for GfxWorld; (4) noise-fixup
discipline in conv_cells + verbatim pass-through for data words; (5) the
CONSOLE-side gfx interior model for the final encode (raid console rt(planes)
= linear + 749,115, GX2-side majority; skate derivability = fit a formula
over PC-known counts on raid+dock, else 2-map constants).

## ADDENDUM 7 (directive session 3, part A complete): clipMap BLOCK-MODEL FIX — both gates clean mod typed classes
Chasing the dockside (16,12) family to its allocation site uncovered — and fixed —
an **absolute error in the clipMap interior model that the gate could not see**
(both sims biased identically → stream-space compare cancels; but OUR EMITTED
aliases would be absolutely wrong at boot).

**Root cause (OAT T6 load db, `clipmap_t_t6_load_db.cpp` + `ZoneInputStream.cpp`
+ `ZoneConstantsT6.h`):** the old `clipmap_events` walker modeled several
allocations wrongly:
- inline **MapEnts root (36 B) and PhysPreset roots (84 B) load into TEMP**
  (asset LoadPtr pushes `SwapEndianness()?VIRTUAL:TEMP` — native console/PC =
  TEMP): file bytes, ZERO virtual;
- **INSERT-typed pointers allocate a 4-byte virtual slot**
  (`InsertPointerAliasLookup`, INSERT_BLOCK = XFILE_BLOCK_VIRTUAL) — mapEnts is
  INSERT on all four zones;
- real aligns: **aabbTrees 16, brushes (cbrush_array_t) 128, box_brush 16,
  triEdgeIsWalkable 1** (walker had 4 everywhere).
NEW event kind `('temp', rel, size)` in alloc_events/replay_events/_event_fine.

**Anchor machinery that proved it (reusable):** (1) `AddPointerLookup` field
semantics — a dedup alias targets the FIRST occurrence's FIELD address: dockside
DynEntityDef physPreset dedups (12 ptrs) must land exactly on owner_def+56
(owners #200/#204/#215); (2) **cbrush sides/verts offset-pointers** are plain
linker-truth block offsets — thousands per map, must land mod-12 = 0 on the
brushsides/brushverts grids; (3) the material-name content sweep. Under the OLD
model: raid grid mod 8, dock mod 4, dock defs off by 660 (console) / 640 (PC).
Under the NEW model + re-derived constants: **all grids mod-0 on both maps,
dock preset aliases exactly owner+56, and the name sweep becomes UNAMBIGUOUS
(raid console 223/223 single peak; raid PC unique 223/223 at −440 across
±20,000; dock PC unique 221/222 at −644)** — the old "false peak at 922,000"
was the TRUE value; the old baked constants were absolutely off by +2,132
(raid) / +644 (dock).

**Re-baked constants** (raid_oracle_control): raid GEN pre_skip 92→2,224,
lump 7,816→5,628; PC pre −2,574→−440, lump −2,228. dock GEN pre 4,952→4,308,
lump −492→+344; dock PC pre −644 (phase-pinned by the 222 brushside-plane
self-ref family: mod-12 grid ambiguity broken by ours==gen), lump −88.
NOTE: interior consumption is now **frame-phase-dependent** (16/128 aligns) —
a pre_skip candidate band repeats mod 12; content anchors or the gate family
pin the phase. PC S_snd anchor family remains noisy (raid mode n=5) — PC lumps
are the weakest baked numbers.

**Also in this pass:** `_stringish` min run 2→3 (dockside DD: genuine packed-
verts bytes `~(` NUL read as a "string", blocking the stale-str class on one
of the three consecutive set-string members — the classic DD run, now typed).

**End state:** raid GATE **PASS**; dockside **0 violations** (DD ptr-eq ×4,
clipMap ptr-eq, GWMP ptr-eq) — remaining = 2 MISSING corpus techsets (CAVEATS
§16, registered, dockside-only). ST calibration exact (raid 7009/6 console+PC,
zm_transit 2821/0); alloc_events self-checks all byte-exact. The fp_recompute
float-class note: `_fin_float` is vacuous for block-5-range words (all decode
to |f|≤2) — the effective discriminator is unaligned-window OR
(mid-body-both + diff-asset + gen-not-string); kept, documented.

**STANDING REGRESSION — `python raid_oracle_control.py anchors`** (run after
ANY loader-model/walker change, alongside ST calibration + `python
alloc_events.py`): the absolute-truth anchor suite. It measures each sim
against LINKER TRUTH on all four zones (raid/dock × console/PC): cbrush
sides/verts offset-pointers mod-12 grids (3,164+7,826 raid / 2,236+5,517
dock), the dockside preset field-lookup anchors (12 = owner_def+56 exact),
and the material-name content anchors at the baked frame (223/223 raid,
221/222 dock). Baseline 2026-07-10: ALL PASS. Rationale: the gate compares
stream-space OURS-vs-GEN, which cancels identical bias on both sims — an
absolute model error is gate-invisible and will only ever have accidental
witnesses; these instruments see it directly.

**INVARIANT — frame phase:** interior consumption is frame-phase-dependent
(aabbTrees 16 / brushes 128 / box_brush 16 aligns), so pre_skip candidates
that satisfy the offset-pointer grids repeat mod 12. Grids alone can NEVER
pin a pre_skip — only content anchors (the material-name sweep) or a
gen-match family break the phase ambiguity. Never re-bake a frame constant
from grids alone.

**Boot relevance (why this wasn't cosmetic):** our emitted zones' dedup aliases
into the clipMap interior (dynEnt band and beyond) were absolutely wrong by the
same 640–2,132 bytes on the old model — a silent runtime-fault class that a
blind skate build would have shipped. The corrected model is structural (load-db
derived), so it transfers blind; skate's pre_skip_pc is derivable from skate's
own PC zone via the now-unambiguous material sweep (B prerequisite, done here).

## ADDENDUM 6 (2026-07-10, directive session 3 cont.): (A) LINK-TIME FLOAT-RECOMPUTE class — raid GATE PASS, dockside 221→12
The clipMap/GWMP "diff-asset" residual (ADDENDUM 5) was re-diagnosed and is NOT
content-dedup: it is **link-time float-recompute noise**. Evidence (raid 293):
287/293 4-aligned, 293/293 decode to |f32|<1e-3 near-zero floats, 293/293
resolve MID-body (delta>32) on BOTH sides, and content-compare = all content-
DIFF. These are console-recomputed geometry floats (clipMap `cStaticModel`
invScaledAxis/absBounds; `DynEntityDef` pose; GWMP nodes) that our byte-copy
keeps at PC values; near-zero elements encode into the block-5 byte range and
are FALSELY resolved as pointers.

**New typed class** (`raid_oracle_control.semantic_diff`, `fp_recompute` for
clipMap_t/GameWorldMp; helpers `_fin_float` |f|<=2, `_fp_noncptr`): a mismatched
window is classed iff both decode to finite float |f|<=2 AND
  (a) the window is UNALIGNED (w%4!=0 — can't be a pointer field), OR
  (b) NEITHER side is a clean pointer target (both None/#tagged/mid-body>32)
      AND the two sides resolve to DIFFERENT assets (float noise scatters;
      a consistent SAME-asset delta is a real pointer — NOT classed)
      AND the genuine target is not string-content (guards real string dedups).
Guards verified: excluding same-asset correctly kept the dockside (16,12) real
+16 family OUT of the class (reappears as 12 ptrbad, as intended).

**Results**: raid **GATE PASS** (clipMap 293→0 ptrbad = 450 classed words;
GWMP 1→0). dockside clipMap 221→12, GWMP 1→0. ST/self-checks unchanged
(alloc_events + xmodel 440/440, 491/491).

**Dockside residual (NOT float-noise, correctly left as violations)**:
1. **clipMap 12 ptrbad** — the (16,12) family: self-referential clipMap
   pointers (dynEntDef+56 physPreset* region) that OUR assemble emits **+16**
   in stream/runtime vs genuine. LOCALIZED: intra-clipMap omap AGREES at the
   target (our_rt−gen_rt delta 0 until clip-rel 2,904,064 where the known
   dynEnt lump 492 appears) ⇒ the +16 is in `produce_nobackbone`'s PC→console
   RELOCATION of these dynEnt-region self-pointers, not the interior alloc
   model (align-16 on the DynEntityDef array had no effect). A real bug to fix
   in the assemble's dynEnt reloc; precisely bounded (12 ptrs, one region,
   constant +16). Per the directive: chase to the reloc site, do NOT class.
2. **DestructibleDef 1 ptrbad** (off 144): OURS holds a near-zero float,
   GENUINE holds a string-dedup pointer (target IS stringish) — a genuine
   emit divergence, correctly NOT classed (both string-guarded branches
   refuse it). 1 pointer.
3. **2 MISSING techsets** (@0x89e00da, @0x89e1b64): pre-existing corpus gap
   (CAVEATS §16), separate from the pointer model.
Not a gate PASS on dockside yet ⇒ PROJECT_STATE NOT updated to PASS.

## ADDENDUM 5 (2026-07-10, directive session 3): interior-event hypothesis FALSIFIED for the residual — residual is CONTENT-DEDUP, not drift
The handoff's single named fix (XModel/FX/techset **interior allocation-event
model** to close the drift-band residual) was BUILT and TESTED for XModel and
**does not move the gate**. Concretely:
- **`alloc_events.xmodel_events`** (NEW) emits one allocation-event list per PC
  XModel (body/name/bone arrays/surface dynamic/collmaps chain), byte-exact vs
  `xmodel_pc.parse_xmodel_pc`: **440/440 raid + 491/491 dockside** (self-check in
  `alloc_events._xmodel_selfcheck`, wired into `python alloc_events.py`).
- Wiring it into `PC_EVENTS` with **real per-alloc alignment REGRESSED** the gate
  (raid clipMap 293→11,503 ptrbad, GWMP 1→444). Total align pad it adds on raid
  = **3,400 B**, i.e. ~1/30th of the 105,045 pre-GfxWorld deficit — the loader
  PACKS XModel FOLLOW arrays (as the xmodel_convert docstring already states);
  the pads are spurious and shift the whole post-XModel region.
- Wiring it **packed** (granular anchors, zero pad, `xmodel_events(..., packed=
  True)`) is **EXACTLY NEUTRAL** — raid stays 2 violations / clipMap 293 / GWMP 1
  / unresolved 24,671, byte-identical to baseline. rt-values are unchanged and
  the failing pointers do NOT target XModel interiors.
- **Diagnosis of the residual** (raid `DEBUG_ROOTS=('clipMap_t',)` delta-diff
  histogram): **`[('diff-asset', 292), (-9208951, 1)]`** — 292 of 293 failing
  clipMap ptrbad resolve to a **DIFFERENT ASSET** ours-vs-gen (ours→XMODEL 106 /
  gen→XMODEL 110; ours→FX 121 / gen→FX 124; ours→XMODEL 174 / gen→XMODEL 189;
  ours→TECHNIQUE_SET / gen→GFXWORLD, …). Dockside mirror: **`[('diff-asset',
  208), (16, 12), (-7507346, 1)]`**.
- **Conclusion**: the clipMap/GWMP residual is the SAME **cross-asset content-
  dedup** class already retired for DestructibleDef (ADDENDUM 4) — the linker
  replaced a value with a pointer to whichever earlier byte-identical blob it saw
  first, and PC vs console have different asset content/order so the dedup lands
  on a different asset. It is NOT an interior-alignment drift and is NOT closable
  by an interior event model. The correct disposition is to TYPE it as a content-
  dedup class (verify content-equality at the two targets first), exactly as DD.
- **Genuinely-interior candidate, small**: dockside's `(16, 12)` group = 12
  pointers with a constant +16 same-asset delta — that IS an alignment/skip miss
  worth closing, but it is 12 of 221, not the mechanism.
- **Standing / state**: gate baseline UNCHANGED (raid 2 / dockside 3+2, unresolved
  24,671 / 19,926). `xmodel_events` + `packed` param kept as verified dormant
  tooling (safe, neutral; a candidate for the assemble's granular string re-
  sourcing). ST calibration untouched. **The handoff's "one interior event list
  closes the residual AND unresolved→0" premise is falsified for the clipMap/GWMP
  residual; unresolved→0 remains gated on the PC GfxWorld interior VIRTUAL model
  (ADDENDUM 1/3), a separate mechanism.**


## ADDENDUM (same day): Track F emit INTEGRATED
- `produce_nobackbone` GfxWorld row now emits via `gfxworld_emit.emit_gfxworld`
  (cached per offset; fixups rewritten through the shared omap each pass).
  raid 21.8 MB / skate 22.6 MB; **skate assemble has ZERO missing rows** —
  first full-coverage emit. Gate: GfxWorld pairs as allowlisted (fast-path,
  no 22 MB byte-diff); violations unchanged (DD ×6 + GWMP 1 + clipMap 1).
- `material_convert.INLINE_TECHSET_HOOK` (installed by the assemble): materials
  whose techniqueSet ptr is FOLLOW/INSERT get the Track B substitute blob
  EMITTED IN PLACE (loadability req., CAVEATS_gfxworld_trackF §Integration).
  Resolver = manifest → corpus exact-name → struct_fallback. NOTE: raid's 352
  materialMemory inline materials all ALIAS their techsets (slot refs; region
  re-parses end-exact) — the hook only fires on FOLLOW-techset zones (zm /
  attachment class); not yet exercised by an oracle zone.
- drawSurf fix: PC u64 @16 is stored VERBATIM on console — `>Q` swap removed
  in `material_convert.convert_material`/`deconvert_material`; Track F's
  compensating patch removed from `gfxworld_regions.conv_material_memory`.
  Material oracle unchanged (437/446 exact, round-trip 28/28 — standalone
  materials carry drawSurf 0, so the old swap only corrupted GfxWorld inlines).
- **Post-integration bar NOT fully met**: unresolved is 24,671 (raid) /
  32,411 (skate), all attributable, ~all `unres:GfxWorld` = refs INTO the
  GfxWorld interior (from clipMap planes, GWMP, SndBank, XModels + the emit's
  own interior self-fixups). Resolving them needs the **PC GfxWorld interior
  VIRTUAL model**: which PC regions consume no virtual (the −10.4 MB) and the
  per-region PC-runtime bases, so pc_inv can invert rt values inside GfxWorld.
  Measured but unsolved: subset-sums of region sizes near 10.4 MB are ambiguous
  (probes+vd0+idx ≈ 10.27 M, lm+smodelDrawInsts+idx ≈ 10.45 M, …); the
  gen-pairing anchor fit found only ~26 usable pairs (float noise). Suggested
  next: per-region anchors from structural refs (clipMap hdr planes ptr pins
  dpvsPlanes at PC-rt 66,019,436 on raid = 100,213 below the linear-sim gfx
  start) + console-side region layout via a G2 console-marks walk of the
  genuine zone. Until then those refs stay TAGGED poison (zone not bootable).

Executes `HANDOFF_assemble_runtime_interior_model.md`. Gate on raid went from
9 pointer-only violations (GWMP 526 / clipMap 28,191 / ComWorld 3 / DD 222 ptrbad)
to **8 violations = DD ×6 (222) + GWMP 1 + clipMap 1 (295 residual)** — everything
else is modeled. ST calibration unchanged (raid 7009/6, transit 2821/0, PC 7009/6).

## ADDENDUM 2 (same day): POLISH integrations
- **Lighting**: `gfxworld_dynamics.conv_world_vertex` tangent now uses
  `lighting_repack.conv_tangent` (cross-lane 1-bit rotate; the old swap2 was
  wrong on ~99.3% of verts = the "renders darker" root cause), inherited by
  the grouped vd0 path; `gfxworld_emit` vd1 now uses
  `lighting_repack.vd1_groups`+`conv_vd1` (per-group f16 UV swap2 + RGBA8
  color VERBATIM; the old flat swap2 byte-reversed every vertex color).
  Both 100% byte-exact raid+dockside (lighting_repack_validate.py).
- **SndBank**: `smalls_convert.convert_sndbank` no longer byte-copies the PC
  loadedAssets region (it's uninitialized PC linker heap; genuine console is
  a ZEROED runtime buffer) — entries+data emitted as zeros with entryCount =
  PC verbatim and dataSize = align2048(PC×0.21)
  (`sndbank_audio_convert.console_zone_fields`). raid bank 59.7→13.6 MB,
  skate assemble total 115→99.6 MB. NEW `smalls_convert.author_english_bank`
  authors the `mpl_<map>.english` insert bank (genuine-raid body template,
  alias tables emptied, name/zone/language strings re-authored; parses
  end-exact under sndbank_probe BE) — wiring the extra SOUND list row is a
  container-authoring item. Per the findings: SAB ids ≠ zone assetIds is
  GENUINE behavior, left untouched.
- CAVEAT (pre-existing, now explicit): convert_sndbank still copies the bank
  HEAD/alias region in PC byte order (LE) — the "byte-identical" claim in its
  old docstring is false vs the BE genuine banks; a field-aware BE swap of
  SndBank head/aliases is an open converter item (allowlisted at the gate,
  but required for sound at boot).
- Gate/skate/ST regression after both integrations: unchanged
  (8 violations — DD ×6, GWMP 1, clipMap 1; ST 7009/6).

## ADDENDUM 4 (same day, directive session 2): DD RECLASSIFIED — gate at 2/3 violations
- **The "DD→XModel geometry share map" premise is RETIRED.** Field-mapping the
  222 failing raid DD pointers against the T6 structs shows they are ALL the
  `set string` members (breakSound/breakNotify/loopSound/damageSound per
  stage/piece). And the GENUINE console values themselves DANGLE: raid's
  point into the luxury-sedan XModel's packed verts (no string anywhere within
  ±3.5 KB; the model contains no sound strings at all), the PC twins point at
  FX zero-fill. These are STALE-DEDUP values on absent strings — linker heap
  reuse, shipped by genuine consoles, tolerated at runtime. Our emit dangles
  equivalently (functionally identical). Gate: typed 'stale-str' class for
  DestructibleDef (gen target not string-like ⇒ classed). Raid DD 6→0
  violations (8 ptr-eq, 240 classed words); dockside 2→1 (one remaining
  ptrbad whose gen target IS string-like = the drift-band dedup family).
- **XAnimParts +6 root-caused (pre-blind-build item DONE)**: dockside
  `fxanim_gp_seagull_circle_02_anim` — the console anim has ONE extra frame
  index (count 0x8e vs PC 0x8d; +2 B in each of 3 index arrays). Source
  recompile divergence, NOT a converter bug (6/7 dockside anims byte-exact;
  raid 2/2). Gate rule 'anim-recompile': length mismatch allowed only when
  gen == ours + ≤8 small gen-side insertions (difflib-verified).
- **Interior pass 2 (DPVS-mirror arithmetic): TESTED, DOES NOT CLOSE.** The
  OAT T6 ZoneCode runtime family (cellCasterBits, sceneDynModel/Brush,
  primaryLight[Ent|DynEnt]ShadowVis, sceneEntCellBits, probe/lightmap
  textures, smodel/surface visData ×3 + cameraSaved + casts*, surfaceMaterials,
  dynEntCellBits/VisData) evaluates on raid's counts (plc=6, sunIdx=1,
  cellCount=47, smc=4668, ssc=5194, smvdc=4736, svdc=5248, wc=[19,0],
  dec=[580,0]) to ≈338 KB — NOT the console 919,776 and not positioned to
  give +749,115 before planes (nothing runtime precedes dpvsPlanes in the
  ZoneCode order). Conclusion: the console GfxWorld runtime majority is
  CONSOLE-SPECIFIC allocation (GX2-side, outside OAT's PC model); closing the
  composition needs console-executable RE or a denser anchor family. The PC
  63,283 residual also remains open (mm has no inline images on raid; PC
  runtime family likely lives in PC block 1 — header 516,928 — not virtual).
- **Gate state after this session**: raid VIOLATION = 2 (GWMP name-dedup ×1 +
  clipMap 293), dockside = 3 (GWMP 1 + clipMap 221 + DD 1) + 2 MISSING
  corpus techsets. Every remaining ptrbad is the SAME mechanism: string/name
  dedups resolved through the XModel/techset interior drift band ⇒ the
  single remaining fix is the **XModel (+FX/techset) interior event model on
  both sims** — which is also what unresolved→0 (PC GfxWorld interior) and
  the drift-band guard margin wait on. `raid_oracle_control.py dockside`
  runs the second-map gate (constants baked as DOCK_*).

## ADDENDUM 3 (same day): dockside walk FIXED — model 2-MAP VALIDATED
- **Genuine dockside now walks to EOF** (802 spans, 0 leftover). The @758 break
  was the generic console GfxWorld walk: fixed by dispatching console GfxWorld
  to the G2 region walk (`gfxworld_console_span.py`, NEW) with (a) a skyBox
  string RESYNC in `gfxworld_probe2` (streamInfo's serialized extent exceeds
  its counts by a map-variable 0/+20), (b) a bounds-validated RESYNC at cells
  (dockside serializes planeCount−1 dpvsPlanes — verified: the last plane
  record ends 20 bytes before the nodes), (c) the span tail bounded by the
  GameWorld PathData signature (raid tail = 11,341 B SSkinShaders; dockside
  carries ~12.45 MB of gfx content the probe doesn't model — 36-B placement
  records + image pixel runs + the skinshader block; hopped, treated as
  linear interior).
- **2-map validation of the runtime model**: dockside SndBank anchors = ONE
  exact constant 569,444 (10,787 anchors); GWMP joint solve gives
  (G, C_pc) = (564,984, −15,409,056); dockside oracle gate (first ever;
  `raid_oracle_control.main(co_path=…, pc_path=…)` now parametrized) confirms:
  GWMP 674/675 ptr-ok, clipMap 10,695 ok / 221 residual (raid's 295 class),
  DD ×2 (the share class, 293 ptrs). Dockside constants (gate-confirmed):
  gfx_skip 564,984 / clipMap pre_skip 4,952 / dynEnt lump **−492** (negative
  lumps now supported in alloc_events).
- **Calibration recipe** (`loader_sim.derive_gen_policy`): S_snd exact from
  SndBank anchors; S_clip from the material-name sweep BUT the sweep has
  whole-string false peaks on BOTH maps (raid picks 922,000 vs true 919,868;
  dockside 569,292 vs true 569,936) — the oracle gate's clipMap delta-diff
  histogram is the closing instrument (a single constant offset = the S_clip
  correction). G from the GWMP plateau (mod-16; within-asset deltas cancel).
- **PC GfxWorld interior model (directive item 1) — hard measurements, NOT
  closed**: console runtime allocs are MID-gfx, not an end lump (the 16,733
  plane-family anchors put +749,115 of runtime before the planes region);
  PC pre-planes deficit = 105,045 (pre-GfxWorld, planes pin); the Track F
  image-class region sum (probes+lightmaps+outdoor = 10,234,048) verifies
  against the anchors to within **63,283 of the required 10,297,331** — one
  allocation class is still missing; region identities alone don't close it.
- New caveats registered (CAVEATS_nobackbone_boot §14–16): INLINE_TECHSET_HOOK
  blind path (skate fires it exactly once: hdr_create_lut2dv_827z0f8q);
  dockside XAnimParts +6-byte converter defect (1 asset); 2 dockside techsets
  with no corpus blob.

## 1. Event walkers (`native_linker/alloc_events.py`, NEW)
`clipmap_events` / `gwmp_events` / `sndbank_events`: endian-parametrized, one
allocation-event list per asset — `('seg', rel_off, size, align)` file bytes,
`('skip', size, align)` runtime-only. Self-check `python alloc_events.py`:
byte-exact vs the validated probes on genuine raid (clipMap 12,285 events, GWMP,
SndBank ×2) AND PC raid (incl. the PC-only SndBank trailing zero pad, emitted as
a pad seg). PC and console event lists are IDENTICAL on raid clipMap (12,285 segs,
same sizes) — confirming byte-identical serialization at allocation granularity.

`loader_sim.replay_events` replays them: per-seg runtime align + registration,
skips advance the virtual cursor with no file bytes. Wired into the console sim
(`CONSOLE_EVENTS`), the PC sim (`PC_EVENTS`), and hence our-stream pass-3.
Effect: genuine raid SndBank anchors (12,079 SndAlias name→list-name pairs, exact
pairing) collapse from a 360 B spread to ONE constant — 927,684 with skips off.

## 2. Solved constants (raid; baked as defaults in `raid_oracle_control`)
- console `gfx_skip = 919,776` after GfxWorld (GWMP tree plateau; ±16 grid broken
  by the joint solve below).
- console clipMap `pre_skip = 92` at clipMap load start. PROOF: with 0, genuine
  material-name dedup aliases invert to mid-string; target−92 is a clean
  NUL-preceded string start (203/223). Origin unknown (unmodeled console alloc).
- console `dynent lump = 7,816` (= 927,684 − 919,776 − 92), one skip before the
  constraints section. Per-list dynEnt element sizes remain unsplit — no anchor
  distinguishes the individual pose/client/server/coll skips (nothing registers
  between them), so the lump IS the model.
- PC `gfx_skip_pc = −10,402,376`: PC GfxWorld consumes ~10.4 MB LESS virtual than
  stream (PC zone header confirms: declared virtual 145,535,968 vs 1:1-sim
  155,942,162). Solved EXACTLY by row-pairing the 516 GWMP tree child aliases
  console↔PC (same dedup, byte-identical serialization): candidates (G, C) =
  (919,776, −10,402,376) / 16-grid; the gate's within-asset deltas picked it.
- PC clipMap `pre_skip_pc = −2,574` (residual to the PC SndBank anchor family
  ≈ −10,404,95x; family is dedup-noisy ±60, so this one is approximate).

## 3. Gate resolution fixes (`raid_oracle_control.py`)
- **Stream-space deltas**: PtrResolver now inverts each side's own omap
  (runtime→stream) before pairing. Runtime deltas are NOT comparable across
  sides — interior align pads depend on the cursor phase at asset start
  (measured +3 GWMP, +95 clipMap). This alone took GWMP 518→1.
- Window choice: an ours-tagged + gen-GFXWORLD window is the pending class and
  outranks misaligned byte views that happen to resolve on both sides.
- '#tagged' poison values recognized by the resolver; tagged + gen→techset-
  INTERIOR classed (substituted blobs are unreproducible-by-design interiors).
- Content-compare fallback fetches 48 B and compares C-strings up to the NUL.
- hard_ok predicates also apply to pointer-shaped float-drift windows.

## 4. Assemble fixes (`produce_nobackbone.py`)
- `Omap.gfx_pc_rt_span` guard (+ `gfx_guard_lo_margin=196,608`): PC-RUNTIME
  values inside PC GfxWorld tag immediately (pre-inversion) — inversion used to
  scatter them into neighboring assets. The lo-margin covers the pre-GfxWorld
  drift band (PC plane array straddles the simulated GfxWorld start by ~100 K —
  the verbatim techsets before GfxWorld under-consume virtual vs stream).
- PC techset spans are OPAQUE in reloc (substituted blobs: linear interior
  deltas are garbage) → string re-sourcing or tagging.
- **String re-sourcing**: unmappable PC targets that are C-strings are re-pointed
  at the same string in our own previous-pass emitted stream.
- **Event-fine regions**: PC↔ours allocation events paired 1:1 per asset for
  clipMap/GWMP/SndBank (`_event_fine`), bisect-indexed `_fine_lookup`.
- **Element-scaled regions**: `xmodel_convert` emits marks (verts0 PC 32 B →
  console 24 B per vertex; triIndices linear); `Omap.add_scaled` maps pointers
  to PC vertex k onto console vertex k. 1,931 pointers routed on skate.
- Values outside every PC span pass through unchanged (float −1.0 = 0xBF800000
  parses in the alias range; poisoning them corrupted content).

## 5. Remaining (named, measured)
- **DestructibleDef ×6 (222 ptrs)** — the geometry-share class, now precisely
  characterized: the PC linker CONTENT-dedups DD piece pointers (e.g. into an
  FX's inline zeros that byte-match the PC float verts), console dedups into the
  XModel's PACKED verts. The semantic target is NOT recoverable from the PC
  value; needs the structural destructible→XModel share map (which DD fields
  reference which XModel array), then emit via the scaled marks.
- GWMP 1 + clipMap 1 (295): asset-name / misc dedup pointers into the
  pre-GfxWorld drift band (PC XModel/techset region under-consumption, ~100 K by
  GfxWorld start, origin unmodeled) — same disease as DD, smaller.
- **2-map validation OPEN**: genuine dockside sim desyncs BEFORE clipMap
  (pre-existing "@758" break — bytes at the clipMap span are floats, i.e. an
  earlier asset mis-walks). Until that is fixed the new constants are
  raid-validated only. zm_transit ST stays exact; skate blind assemble passes
  the fatal bar with ALL 23,375 unresolved attributable (GfxWorld 23,028 +
  techset-interior 347; the old 573 'outside' class is GONE).
- PC SndBank anchor family noise (±60) leaves `pre_skip_pc` approximate; a
  clean PC post-clipMap anchor would pin it.
