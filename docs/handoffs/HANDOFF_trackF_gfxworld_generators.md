# HANDOFF — TRACK F: GfxWorld region generators (the last missing emit row)

Standalone worker doc, 2026-07-09. You produce the console GfxWorld body for the no-backbone
assemble. Everything else in the zone already emits (mp_skate 112.2 MB, all types except
GfxWorld); the assemble session is closing its gate in parallel and will CALL your code.
The old `HANDOFF_trackF_nobackbone.md` drifted into an assemble log — use it only for the
quantified frontier sections cited below; THIS doc is current.

## File ownership (hard boundary)
- You OWN: `native_linker/gfxworld_convert.py`, `gfxworld_body.py`, `gfxworld_assemble.py`,
  `gfxworld_dynamics.py`, `gfxworld_pc.py` (+ new `gfxworld_*.py` you create).
- You do NOT edit: `produce_nobackbone.py`, `pc_to_console.py`, `raid_oracle_control.py`,
  `pc_walk.py`, `walker.py`, `smalls_convert.py`, converter files. The assemble session
  integrates your generators behind a function interface (see "Interface" below).

## The frontier, quantified (raid GfxWorld = 22.25 MB; ~48% already PC-convertible)
| Bucket | Size | What it is | Approach |
|---|---|---|---|
| A. GX2 textures | ~7.2 MB | draw.reflectionProbes (5.0 MB cubemaps), draw.lightmaps (1.57 MB), outdoorImage (0.26 MB), tail material inline (0.26 MB) | EXISTING image pipeline (`ipak_stream`, gx2_texture). Cubemap path pre-verified: tileMode=4, `slice_index` per face, detile→tile round-trip **byte-exact 6/6 faces**. Remaining = per-face loop + GX2 header synth. Not a new unknown. |
| B. smodelDrawInsts | 3.69 MB | GfxStaticModelDrawInst console 208B vs PC 152B | Structural repack, field map already pinned (see below). The real bounded work. |
| C. PC-sourced conversions | ~0.5 MB | materialMemory (0.32 MB, inline materials), cells (0.20 MB, portals/aabbTrees) | Converter-shaped; PC source exists. |
| D. Novel synthesis | ~90 KB | streamInfo.aabbTrees/leafRefs (77 KB), dpvs.sortedSurfIndex (10 KB console sort), dpvs.smodelCastsShadow (5 KB) | The only true console-only content. Derive from PC data; validate vs raid oracle. |

`gfxworld_convert.convert_region` returns None for method in {reorder_pc, console_gx2, reuse,
gen} and fields-without-swap — those are exactly the rows to fill.

## B — smodelDrawInsts field map (pinned 2026-07-07, don't re-derive)
Console:PC offsets — cullDist@0, placement@4 [console 4..32 = **28B GfxPackedPlacement** vs PC
4..56 = 52B GfxPlacement — axis matrix PACKED on console], model@(32:56), flags@(36:60),
invScaleSq@(40:64), lightingHandle@(44:68), colorsIndex u16@(46:70), lightingSH@(48:72),
primaryLightIndex u8@(72:96), visibility@(73:97), reflectionProbeIndex@(74:98), smid@(76:100),
lmapVertexInfo[4]@(80:104) each **32B console : 12B PC**, + trailing lmapVertexColors (walk
parses these; 2052 FOLLOW on mp_skate; walk-validated modelAliasOK 85/85).
Two real conversions: (a) the 52→28 placement packing — recover the console matrix→packed
encoding from genuine raid instances (you have thousands of oracle samples; solve it as data,
not as docs), (b) lmapVertexInfo 12→32 expansion.
**Stub fallback stands:** a zeroed/count-0 smodelDrawInsts is acceptable for boot #1 (base
world renders from surfaces/vd0 without static props). Don't let (a) block the artifact.

## Validation bars (per house rules)
- Buckets A–C have genuine console counterparts → **byte-exact vs the raid oracle**, then
  spot-check on a SECOND oracle map (dockside or nuketown) — a rule validated only on raid is
  not validated.
- Bucket D: byte-exact vs raid oracle where deterministic; where a sort/derivation is
  ambiguous, reproduce genuine raid exactly first, then confirm the same rule reproduces the
  second map.
- Model refs / techset refs inside regions: expect list-index/alias behavior (Track A's
  gfxworld_remap found shared refs resolve by asset-list index) — but Track A was the
  genuine-inline transplant, NOT this converter; reuse its findings (DELTA/list-index remap in
  `wiiu_ref/gfxworld_remap.py`), not its code path.
- **Pointer VALUES are not your problem.** Emit region bytes + alias fixups; the assemble's
  loader-simulation pass (FINDINGS_loader_sim_pointer_model.md) rewrites pointers. Don't
  hand-encode runtime addresses.

## Interface with the assemble session
Deliver a function (in your files) shaped like: `emit_gfxworld(pc_zone, ctx) → (bytes, fixups,
per-region log)` in console serialization order, with per-region method tags and explicit
STUB markers for anything stubbed. The assemble session wires the call. Agree the exact
signature with them via the user before your first integration run; after that, your emitted
bytes are judged by their raid gate (allowlist applies to your regions like everyone else's).

## Order of work
1. Bucket C (small, converter-shaped — warms up the region harness).
2. Bucket A GX2 routing (biggest MB, lowest risk, machinery exists).
3. Bucket D synthesis (small, oracle-backed).
4. Bucket B smodelDrawInsts (hardest; stub first, integrate, then solve the packing).
Rationale: 1–3 + a B-stub gives the assemble session a COMPLETE GfxWorld emit early — the
artifact stops being blocked on you while you crack the placement packing.

## Constraints (standing)
Never write under `E:\`. struct_layout is WRONG for GfxWorld draw-onward — trust probes +
the pinned field maps. Chase to root on any resync drift. Keep PROJECT_STATE.md + CAVEATS
truthful (mark every stub in CAVEATS so boot #1 is read correctly).

## Definition of done
All raid GfxWorld regions emit byte-exact vs oracle (mod allowlist/pointer classes) with
second-map spot-checks, OR are explicit registered stubs; mp_skate GfxWorld emits
self-consistently through the same path; the assemble session's gate accepts your regions;
smodelDrawInsts either solved or stubbed-with-plan. That completes zone coverage — the last
row before container → pack → first boot.
