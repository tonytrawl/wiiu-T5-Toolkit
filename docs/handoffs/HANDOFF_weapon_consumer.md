> **✅ RESOLVED 2026-07-09 — SPAN BAR DONE.** All zones walk end-to-end: mp_raid 887, mp_skate 840,
> nuketown 840, zm_nuked 3158, zm_transit 3254; console mp_raid round-trip stays byte-identical.
> No `weaponvariantdef_pc.py` was needed — the generic walker + ZC directives carry WEAPON /
> WEAPON_CAMO / MENULIST once these were fixed (see memory `trackE-pc-walk-dispatcher` for detail):
> ASSET_ROOT "WEAPON"/"WEAPON_CAMO" mappings; `ptr2` double-pointer arrays (attachments 63 /
> attachmentUniques 95 / szXAnims 88 / gunXModel 16...); enum-constant counts (NUM_WEAP_ANIMS);
> partial `reorder: ...` semantics + accumulating reorder blocks (WeaponDef has two); a new
> `Walker.asset_span` hook for FOLLOW/INSERT inline full assets (TracerDef.material, attachment
> XModels, WeaponDef.hudIcon material); menuDef_t union directive aliases + ctx propagation;
> inline techset inside Material (`convert_material` now consumes it); clipMap PhysConstraint
> dynamics (rope materials, zm_transit).
> **Files touched:** `wiiu_ref/walker.py`, `wiiu_ref/struct_layout.py`, `wiiu_ref/clipmap_probe.py`,
> `native_linker/pc_walk.py` (asset_span registration + spans collection), `native_linker/material_convert.py`,
> `native_linker/clipmap_pc.py`, new debug tool `native_linker/weapon_trace.py`.
> **Assemble session:** pc_walk.py edited — pick up these changes; do not edit concurrently.
> **Remaining (zombies boot):** the CONVERT bar — PC→console WEAPON body conversion vs the
> zm_transit/zm_nuked matched-pair oracle.

# HANDOFF — WEAPON (WeaponVariantDef) PC consumer + converter

Standalone doc. Goal: make the PC walk **traverse and convert inline WEAPON assets** so maps that
carry them reach end-of-zone and assemble. This is the **universal walk-terminal gate** — not
zombies-specific: it blocks **nuketown (MP, 1 inline weapon)** and **every ZM map (~100/zm)**. Runs
independently of the mp_skate no-backbone build (mp_skate has 0 inline weapons, so it walks without
this — but confirm with a `flags`/type scan, since the "MP aliases from common_mp" assumption has
already proven wrong once).

## Why this exists (root cause, already traced)
The PC walk drifts because inline WEAPON assets have `root=None` in `pc_walk` → no consumer → the
walker **skips them (0 bytes)** → everything downstream desyncs into garbage, surfacing ~13 assets
later as a *different* asset's "drift" (nuketown's was misread as XANIMPARTS@801; the real culprit is
the WEAPON at 788). So the visible symptom is downstream — the fix is a real WEAPON extent consumer.

Inline WEAPON counts (hp=FOLLOW, no consumer today):
| map | WEAPON | WEAPON_CAMO |
|---|---|---|
| nuketown (MP) | 1 | 0 |
| zm_nuked | 98 | 31 |
| zm_transit | 107 | 29 |
| mp_skate | 0 | 0 |

## Scope
`WeaponVariantDef` load_db is ~2033 lines (~200 loads), nesting XModel / Material / FxEffectDef /
TracerDef / WeaponAttachment[Unique] / WeaponCamo. **BUT** in a map zone the sub-assets are **mostly
aliased** (like the FX/material inline cases already handled) — so the bulk is the **flat struct +
string tables + a few inline arrays**, not deep nested synthesis. Two consumers needed:
`native_linker/weaponvariantdef_pc.py` (WEAPON) + a WEAPON_CAMO consumer.

## Two bars — separate them (same lesson as XModel/skinned)
1. **Span (for the walk)** — REQUIRED first. You must size each WEAPON body correctly so the walk
   resyncs onto the next asset. A truncated/mis-sized body corrupts the stream → not loadable. This is
   the immediate gate and the whole reason the walk drifts.
2. **Convert (PC→console body)** — needed for a *bootable* zombies map, but can follow the span. Most
   fields are scalar/string byte-swaps + aliased-ref relocation.

## Method (the proven discipline)
- **Read the emission/consume order from OAT** — `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/
  weapon/weaponvariantdef_t6_load_db.cpp` (and the console write_db) is the authoritative field/block
  sequence. Diff your span parser against it (the OAT-load-order diff method that cracked every
  dispatcher drift with no rebuild). Do NOT hand-derive offsets from bytes — read the codegen.
- **Aliased sub-assets consume 0 bytes** (hp/ptr ≠ FOLLOW → skip), inline ones you recurse into. Reuse
  `pc_walk`'s existing alias-skip logic and the inline-material / inline-image span helpers
  (`material_convert.pc_image_span`, etc.) for the sub-assets that ARE inline.
- **Matched-pair oracle for the converter** — WEAPON assets live inline in the **ZM map zone itself**
  (self-contained; NOT common_zm), so validate against `zm_transit`/`zm_nuked` console vs PC, joined
  by weapon name. (Same mode-dependent oracle rule as XModel.) `validate_material.py` is the pattern.
- **Regression gate** — after each change, raid + mp_skate stay end-to-end, and the console round-trip
  stays byte-identical.

## Pinned facts / traps
- WEAPON is a **console-only-typed** relabel concern: WiiU console type-ids are shifted (console type
  6 = Material) — confirm the WEAPON/WEAPON_CAMO type-ids empirically, don't trust a hardcoded enum.
- The `WeaponAttachmentUnique`/`WeaponCamo` sub-structs are the most nested — check the codegen for
  which are inline vs aliased in a *map* zone (likely aliased); only build inline paths for the ones
  that actually appear inline.
- Some sub-arrays are conditional (count-gated) — mirror the codegen's `if(count)` conditions exactly;
  a wrong conditional is the classic drift (cf. the FX `unknownDef=1 char` and destructible fixes).

## Validation / done-when
- **Span:** the WEAPON/WEAPON_CAMO consumer resyncs onto the next asset across **all** inline weapons
  in zm_transit (107) and zm_nuked (98) → those maps reach **end-of-zone**. nuketown (1 weapon)
  reaches end-of-zone too.
- **Convert:** WEAPON bodies convert and validate vs the ZM-map-zone oracle (byte-exact modulo any
  known lossy sub-fields), and a converted ZM zone resyncs through the genuine console walker.

## Files
`native_linker/pc_walk.py` (register the consumer), new `native_linker/weaponvariantdef_pc.py`
(+ WEAPON_CAMO), `native_linker/validate_material.py` (oracle pattern),
`tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/weapon/weaponvariantdef_t6_load_db.cpp` (the
authoritative order). Oracle zones: `zm_transit`/`zm_nuked` console + PC. Never write under `E:\`.

## Coordination
`pc_walk.py` is also read by the no-backbone assemble session — **only one editor of `pc_walk.py` at a
time.** Announce when you're registering the WEAPON consumer so the assemble session picks it up
rather than editing concurrently.
