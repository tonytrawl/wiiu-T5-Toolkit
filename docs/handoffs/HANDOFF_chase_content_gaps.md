# HANDOFF — CHASE session: content gaps from the raid gate (parallel to loader-sim)

Standalone worker doc. Source of truth for background: `HANDOFF_assemble_pointer_model.md`
§"Remaining per-type violations". These are the raid-gate violations that are REAL content/size
gaps (not pointer artifacts — those are the loader-sim session's job). You deliver findings +
converters in **NEW files only**; the assemble session integrates them.

## File-ownership rule (hard)
- You may CREATE: `native_linker/gsc_swap.py`, probe scripts (`probe_gameworldmp*.py`,
  `diff_clipmap_regions*.py`), findings docs.
- You may NOT edit: `produce_nobackbone.py`, `pc_to_console.py`, `raid_oracle_control.py`,
  `pc_walk.py`, `walker.py`, `struct_layout.py`, `material_convert.py`, `smalls_convert.py`,
  `gfxworld_*.py`. If a fix belongs there, write it up and hand it off.

## Task 1 — GSC endian-swapper (ScriptParseTree ×13) — bounded, boot-relevant
Console GSC = PC GSC byte-swapped, verified on the saved pair
`wiiu_ref/gsc_pair_*_mp_raid_fx.bin` (same length; header words + offset tables swapped; code
region mostly equal). Build `gsc_swap.py`: parse the GSC container enough to know which fields
are u16/u32 (swap) vs byte-code/strings (copy). Bar: **byte-exact vs the genuine console GSC on
ALL 13 raid pairs**, then spot-check on a second map's pairs (nuketown) — do not accept a
raid-only validation. "Code region MOSTLY equal" is a flag: classify every non-equal code byte
(likely embedded u16/u32 operands needing swap) — no unexplained bytes.

## Task 2 — GameWorldMp +66 KB layout gap — probe first, no converter until measured
Genuine console body 308076 vs ours 241860. The WORLD identical-layout assumption fails here —
console PathData has extra/bigger sections. Method: the standard OAT-load-order diff — read the
generated console T6 loader for GameWorldMp/PathData, list its serialization order + per-field
sizes, diff against the PC walk's layout, and locate exactly which arrays grow (+66 KB must
decompose into named fields × counts). Deliverable: a findings doc with the field-level delta
and (if it's a bounded packing change like GfxPlacement 52→28) a conversion spec. Pathfinding
data plausibly matters for boot/AI — treat as required for the playable tier, possibly stub-able
for boot #1 (say which, with evidence).

## Task 3 — clipMap_t interior diff — classify, don't fix yet
Sizes near-match (2238640 vs 2238630) but many hard-diff bytes. Region-level diff (same method
that cracked GfxWorld regions): segment the asset by the console loader's serialization order,
attribute diffs per region, classify each as (a) pointer artifact — hand to loader-sim session,
(b) padding/alignment, (c) real content divergence. Only (c) needs work; spec it, don't patch
shared files.

## Small verifications (do alongside, cheap)
- **DestructibleDef ×8**: 1–6 hard bytes each @~1639 — confirm u16 scriptstring vs float-LSB
  source divergence → allowlist class or 1-line fix spec.
- **Glasses** 9654 vs 9622: check the −16/−32 inline-material class applied to nested GlassDef
  materials explains it exactly → allowlist spec.
- **no-console-pair ×2** (trailing PC techset + material): verify they're console-aliased
  versions → pairing rule for the gate.

## Bars & house rules
Byte-exact-vs-oracle is your bar for everything here (genuine console counterparts exist for
all of it). Validate on ≥2 maps before declaring a rule (raid-luck-masking). Chase to root —
a visible diff is usually downstream of the real bug. Never write under `E:\`. struct_layout
is unreliable for console sizes — trust the generated loaders + probes.

## Definition of done
gsc_swap.py 13/13 byte-exact (+second-map spot-check); GameWorldMp +66 KB fully decomposed into
named fields with a conversion-or-stub recommendation; clipMap diffs classified per region with
only class-(c) items left as specs; the three small verifications resolved to allowlist entries
or fix specs. Hand the bundle to the assemble session for integration.
