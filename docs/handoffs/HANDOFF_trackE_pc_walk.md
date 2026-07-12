# HANDOFF — Track E: PC map-zone walk (dispatcher) → end-of-zone

Standalone start doc. Goal: the PC-side walk resyncs through an **entire** map zone (every asset's
extent found, resyncing onto the next asset's FOLLOW boundary), so a no-backbone map can be traversed
and assembled. This is the gate for the acceptance run AND for reading a no-backbone map (mp_skate)
natively (which decides whether we even need an OAT front-end). Currently **870/887 on mp_raid**,
crash-guarded — one bounded piece (SndBank span + 3 ready dispatches) from the "walks a whole map
zone" milestone.

## The core design (already built — reuse, don't rebuild)
E is a **dispatcher**, not a generic-walker rewrite. Each asset type routes to its validated per-type
probe; only genuinely-new types need new probes. Built modules in `native_linker/`:
- `pc_walk.py` — the dispatcher. Routes each asset by type; **skips aliased assets (header ptr ≠ FOLLOW
  → 0 bytes)**; uses the strong-resync loop (below).
- `fx_pc.py` — `parse_fx_pc` (FxEffectDef 76B / FxElemDef 292B, LE mirror of console `fx_probe`).
- `xmodel_pc.py` — `parse_xmodel_pc` (body+bones+surfaces+collision+boneInfo span; skinned handled).
- `techset_pc.py` — `parse_techset_pc` (codegen-verified emission order; MaterialTechniqueSet=152,
  techniques[36], MaterialTechnique=8+passCount×24, MaterialPass=24).
- `material_convert.py::pc_image_span` — inline-image span, GENERALIZED:
  `body(64) + streamedPartCount(@27)×8 + GfxImageLoadDef(12 + resourceSize)`; `baseSize@12`.
  Locates via name-ptr FOLLOW @+56 (no hash — aliased comma-names have hash=0). loadDef tail only for
  real inline images (texture@body+0 ≠ 0); aliased zeroed stubs carry none.
- `_collmaps_span` (mirrors console `consume_collmaps`; PC physics struct sizes identical).
- DestructibleDef dispatch — the real content is **inline PhysConstraints** (session-1's "2-byte" guess
  was WRONG; asset 747 root cause corrected).
- Converters that double as extent oracles: `material_convert` (Material), `xmodel_convert`, `fx_convert`.

## Remaining to end-of-zone (ordered — smaller than it looks)
1. **PC SndBank span parser** — the one real piece. SndBank is a 4768-B complex type
   (aliases/radverbs/ducks/asset-banks); the console probe `parse_sndbank(…, '<')` **over-reads to ~EOF
   on PC** because the PC SndBank layout differs. Its under-read was masked by a coincidental `next=0`
   (a sound alias sits mid-data at 0x5ced31d).
   - **Span only — NOT a byte-perfect sound converter.** A stub SndBank likely suffices for first boot
     (sound is non-fatal to load — confirm at assemble time). Don't build the converter now.
   - Method: matched-pair oracle (raid has SndBank on both platforms; `console_sndbank_sample.bin`
     captured). Diff PC vs console to find the divergence — same class as Material/XModel (count-width
     or dropped-field). Pin the PC span, resync onto the next asset.
2. **XAnimParts** dispatch — `parse_xanim` is endian-ready; dispatch with `'<'`. (×2 in the tail.)
3. **FootstepTable** — SIMPLE type. (×7.)
4. **IMAGE** — reuse `pc_image_span`. (×6.)
→ end-of-zone milestone on mp_raid.

## The debug method (this is what finds real bugs)
Use the **strong per-type resync**, not a weak next-word check: validate each successor is a *plausible
body for its declared type*, while allowing the known false-positive edge cases (0-surface XModels,
0-element FX, aliased/null names). The weak next-word check MASKS multi-byte cascades — that's how a
2-byte destructible over-read masqueraded as a "767 techset variant," and how the SndBank under-read
hid behind `next=0`. When something "drifts on a techset/type", suspect an **upstream** under-read in a
world-adjacent or complex asset and trace to the true first under-read.

## Pinned facts (do NOT re-derive)
- **Validation target is a MAP zone (mp_raid), not common_mp.** common_mp is the shared backbone
  (aliased, never converted; dominated by menu/weapon/anim — the dispatcher clears only ~120/6272 there
  by design). common_mp IS the matched-pair oracle for per-body Material/XModel *validation* — different
  purpose from the walk.
- **Aliased assets consume 0 bytes** (header ptr ≠ FOLLOW → skip).
- **struct_layout's GfxImage is the wrong variant** — its offsets don't apply. Empirical PC pins:
  width@4, height@6, depth@8, baseSize@12, streamedPartCount@27, name-ptr FOLLOW@56, hash@60.
- Console type-ids are **shifted** (console type 6 = Material) — confirm any type-id empirically.
- **GfxWorld** extent → dispatch to `gfxworld_probe2` (READ-ONLY; the geometry session owns GfxWorld
  conversion). Already handled in the world-asset block dispatched to reach 852.
- Sizes: Material console 104B, XModel body 244B, console XSurface 128B (PC 80B).
- The asset-list array is **NOT 4-aligned** (Track A fix — spurious `(o+3)&~3` removed).
- **Regression gate:** after each change, the console round-trip (`stage1_roundtrip`) must stay
  byte-identical, and Track A must stay 437/446 (+446 round-trip). Re-check every step.

## Acceptance (the real Track E finish line — do NOT skip)
1. End-of-zone on **mp_raid** (the dev target).
2. Then re-run the walk on **mp_nuketown_2020 (PC)** AND a **zm map (zm_transit / zm_nuked)** and confirm
   end-to-end resync on both. This guards against mp_raid-specific luck (the asset-list alignment bug
   hid in raid once already because it "happened to land aligned"). **ZM is weighted most** — zm zones
   are fat/self-contained (hundreds of inline models/materials/techsets), which stresses the XModel /
   material / techset span parsers far harder than raid and will surface any remaining pass/arg/variant
   edge cases.

## Files / rules
- `native_linker/pc_walk.py`, `fx_pc.py`, `xmodel_pc.py`, `techset_pc.py`, `material_convert.py`,
  the collmap/destructible dispatch; `validate_material.py` / `validate_xmodel.py` (oracle pattern).
- Console oracle: `console_sndbank_sample.bin`, console `parse_sndbank`; raid PC + console zones.
- The walk is crash-guarded — nothing is lost handing off mid-item. Never write under `E:\`.

## After end-of-zone
Track E enables reading a no-backbone map natively — re-evaluate whether mp_skate needs a separate OAT
front-end at all (the "native walker drifts @632" on mp_skate is the same maturity problem this walk
solves). Then it feeds Track G (no-backbone assemble).
