# Track B — NEXT: expand the techset corpus, then build signature-fallback

Continuation instructions for the Track B session. Steps 1 & 2 are done
(`native_linker/techset_translate.py`, corpus in `wiiu_ref/techset_corpus/` + `index.json`, 1535
names from 4 zones; exact-name coverage zm_transit 33/34, mp_skate 166/243). Before building the
signature-fallback, **expand the corpus** — the current 4 zones miss most of the platform's terrain
shaders, which is where mp_skate's 75 unmatched `lit_sm_*` blends live.

## Why (the finding)
`lit_sm_*` terrain-blend techsets are **widespread on Wii U, but live in per-MAP zones, not
`common_mp`** — that's why the "not in common_mp" check found nothing. Grep of decrypted console
zones for `lit_sm` (techset count): mp_raid 133, zm_transit 140, **mp_la 127, mp_carrier 104,
mp_dockside 101**. The corpus was built from only common_mp + mp_raid + zm_transit + dockside, so
every other Wii U outdoor map's terrain shaders are missing.

## STEP A — expand the corpus to ALL Wii U zones
Add every genuine console zone you can decrypt, not just 4:
1. **Already decrypted** (use directly): `wiiu_ref/Original FF/mp_la.zone`,
   `wiiu_ref/Original FF/mp_carrier.zone`, `wiiu_ref/Original FF/faction_*_mp.zone`,
   `wiiu_ref/mp_dockside_wiiu.zone`, `wiiu_ref/mp_raid_genuine.zone`,
   `wiiu_ref/zm_transit_original.zone`, `common_mp.zone`, `common_zm` (if present).
2. **Decrypt these Wii U `.ff`** in `wiiu_ref/Original FF/` (stock maps not yet in corpus — outdoor
   maps carry 100+ lit_sm each): `mp_drone, mp_express, mp_hijacked, mp_meltdown, mp_nightclub,
   mp_overflow, mp_slums, mp_socotra, mp_turbine, mp_village`, plus `mp_carrier` if not staged, and
   the `zm_transit_gump_*` set. Use `tools/ff_decrypt.py <ff> <out.zone>` (WiiU v148; these are local,
   not under E:, so decrypt in place is fine).
3. For each zone, run the existing `techset_extract.py` and **merge into the corpus**, keeping the
   extractor's invariant (every blob re-parses to its length, zero alias pointers). Dedup by name;
   keep the `common_mp` copy for shared engine shaders, and keep map-specific `lit_sm_*` from whichever
   zone has them. Extend `index.json` (name → zone/path/size/kind/**signature**).
Expected: the corpus roughly triples, and a large share of mp_skate's 75 `lit_sm` unmatched flip to
exact-name matches.

## STEP B — re-run exact-name match, remeasure
Re-run the enumerator + exact-name match on `mp_skate_pc` and `zm_transit_pc` against the expanded
corpus. Report the new matched / unmatched counts. Use the asset-list sequential walk (reusing
`pc_walk`), NOT a byte-scan (the byte-scan under-counted). Normalize names with `.lstrip(',')`.

## STEP C — characterize the TRUE residue before coding the fallback
For whatever's still unmatched after Step B, decide *why*:
- Compute each unmatched techset's **signature** (slot-mask + passCounts — you already emit `sig`).
- Check whether a **same-signature** console techset exists anywhere in the expanded corpus.
- If yes → it's a name miss, fallback will cover it correctly (see below).
- If NO same-signature exists → that's a genuine Wii U **layer-count / structure ceiling** (the PC
  map uses a richer blend than Wii U ever shipped). Record these explicitly; they're the only ones
  that need a structural down-map (e.g. 4-layer → nearest 3-layer).
Report the split: name-miss (fallback-covered) vs true-ceiling (structural down-map).

## STEP D — build the signature-fallback (`techset_translate.py`)
Key reframe: **for `lit_sm` terrain blends, signature-substitution is CORRECT, not lossy.** A techset
is the *shader* (how to draw); the *textures* are bound separately by the material. Two `lit_sm` blends
with the same structure use the same shader program, so substituting a same-signature console techset
gives the right shader with the map's own textures still bound by the material.
1. Bucket console corpus techsets by `sig` (slot-mask + passCounts).
2. For each unmatched PC techset, pick a same-`sig` console techset → substitute its blob.
3. For true-ceiling cases, down-map to the nearest compatible simpler signature.
4. **Record every fallback** (PC name → chosen console name + sig) so coverage is auditable.
5. Report final coverage: exact-name / signature-substituted / structural-downmap / unresolved(=0 goal).

## Caveats
- **mp_skate's 68% is artificially low** — the PC walk drifts at asset 815 (a Track E `xmodel_pc`
  bad-name-ptr issue), so enumeration is partial past that point. Do NOT over-fit the fallback to a
  partial list; re-measure once Track E clears that drift. Coordinate: that's a Track E fix, not Track B.
- Preserve the zero-alias-pointer invariant on every emitted/substituted blob (re-parse-verify).
- Never write under `E:\` — the local `Original FF/` and repo zones are the corpus sources.

## Files
`native_linker/techset_translate.py`, `wiiu_ref/techset_extract.py`, `wiiu_ref/shader_probe.py`,
`native_linker/techset_pc.py` (enumerator/inline-shader locator), `wiiu_ref/techset_corpus/` +
`index.json`, `tools/ff_decrypt.py`.
