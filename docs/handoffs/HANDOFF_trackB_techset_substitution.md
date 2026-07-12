# HANDOFF — Track B: Techset PC→Wii U (genuine-substitution layer)

Standalone start doc. Goal: give a converted PC map **working Wii U shaders** by substituting the
genuine console techset for each PC techset, matched by name (and by signature for the rest). This
is a required piece for a no-backbone map to boot — without it, every material's techset ref dangles
or points at an untranslated D3D shader. Fully independent of the PC-walk (Track E) work; can run now.

## Decision already made — do NOT recompile shaders
We are **not** doing DXBC→GX2 recompilation. Reason: this is Black Ops 2's own engine shader set, and
Wii U shipped the same game, so a genuine console-native GX2 version of virtually every techset
already exists in the console zones. Substitution reuses the real, engine-correct shader; a DXBC→Latte
recompiler would be a full compiler backend for a dead ISA, rebuilding shaders that already exist.
(If a map ever proves it needs a truly novel shader that signature-match can't cover, revisit for that
one shader only — not as a general converter.)

## What already exists (reuse, don't rebuild)
- `wiiu_ref/techset_extract.py` — extracts genuine console techsets as **self-contained, alias-resolved
  blobs** (301 raid blobs already in `wiiu_ref/techsets_raid/`). This is the substitution primitive.
  Has a `selfcheck()` (~line 744) and `main()` (~line 753); every emitted blob is re-parsed and must
  contain ZERO alias pointers.
- `wiiu_ref/shader_probe.py` — console GX2 techset parser.
- `native_linker/techset_pc.py` — the PC techset parser built during Track E (codegen-verified). It
  already **locates the inline DXBC shaders** in a PC techset — reuse its span/locate logic; don't
  rediscover it.
- OAT writer hook `OAT_TECHSET_DIR` (in the generated `materialtechniqueset_t6_write_db.cpp`) inlines a
  `<name>.techset` blob verbatim — the substitution delivery mechanism if going through OAT; the native
  path inlines equivalently.

## Key facts (verified this effort)
- **Techsets are mostly shared engine shaders** living in `common_mp` (which is on Wii U), not per-map.
  So exact-name substitution covers most of any map.
- **Techset names are the platform-independent join key** (same string PC and console).
- **PC techsets carry INLINE DXBC** (FOLLOW), not aliased pointer refs — confirmed on techset
  "effect_w77q49e8" (a `MaterialVertexShader` with name + DXBC bytecode, programSize=0x2534). The
  console equivalent carries GX2 microcode instead. Substitution swaps the whole techset blob, so you
  never touch the shader bytecode directly.
- Layout: `MaterialTechniqueSet` = 152 B with `techniques[36]` (PC 36 slots; **console 32** — the
  stateBitsEntry 36→32 mirror); `MaterialTechnique` = 8 + passCount×24; `MaterialPass` = 24;
  `MaterialVertexShader`/`PixelShader` = 16 + name + programSize.
- Techsets **alias shared subobjects** (techniques, vertexDecls, literal consts). The extractor already
  resolves these — the invariant "every emitted blob has zero alias pointers, re-parse-verified" MUST
  be preserved.

## The work
1. **Build the corpus.** Extract genuine console techset blobs from every console zone available →
   a `name → blob` library. Sources: `wiiu_ref/mp_raid_genuine.zone`, `common_mp.zone`,
   `zm_transit_original.zone`, `common_zm` (console), any DLC console zones, and the `Original FF/*`
   set. De-dup by name. (techsets_raid is the raid subset; generalize to all zones.)
2. **Exact-name match.** For each PC techset in the target map (enumerate via `techset_pc.py`), look up
   the same name in the corpus → substitute the genuine console blob verbatim. Covers all shared/common
   techsets = most of the map.
3. **Signature-match fallback** for map-unique techsets with no name hit: group console techsets by
   (vertexDecl layout, technique count, pass semantics) and pick a compatible one. Visually approximate
   but structurally valid — it loads and renders. **Record every fallback** so coverage is honest.
4. **Report coverage per map:** matched-by-name / signature-substituted / unmatched.

## Validation / done-when
- Selfcheck the extractor on a genuine zone (all-clean, e.g. raid 172/172).
- For **mp_skate** (the target DLC map): ≥ the common-shader fraction substitutes by exact name, the
  rest map by signature, and there are **zero dangling techset refs** (every material's techset resolves
  to a real console blob). Confirm every emitted blob re-parses with zero alias pointers.
- Cross-check against a second mode (a zm map) since zombies zones are techset-dense and self-contained.

## Files / rules
- `wiiu_ref/techset_extract.py`, `wiiu_ref/shader_probe.py`, `native_linker/techset_pc.py`,
  new `native_linker/techset_translate.py` (the match/substitute layer).
- Corpus source zones under `wiiu_ref/` and repo root; console DLC zones under `E:\...` (copy out,
  read-only, never write under E:).
- OAT is a per-struct byte oracle only — see the OAT clarity tag in `HANDOFF_native_converters.md`;
  it never produced a bootable ff and its own techset write path emits NULL shader subtrees (which is
  exactly why substitution exists).
