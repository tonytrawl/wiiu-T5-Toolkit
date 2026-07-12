# HANDOFF — ASSEMBLE session: gaps CLOSED, gate exposed the pointer-model wall

Continuation of `HANDOFF_assemble_close_gaps.md` (2026-07-09 session). All five named
converter gaps are closed and the raid-oracle gate is BUILT and RUNNING — and it did its
job: it caught the real remaining defect class. **Emitted alias pointer VALUES are wrong
zone-wide** because the assemble loop models block-5 offsets as stream-linear, while the
console loader assigns runtime addresses through a block/alignment allocation model.
This is exactly the `interior_approx` KEY RISK the previous handoff flagged; it is now
proven, quantified, and has a precise fix architecture (below).

## What closed this session (all validated on the raid oracle where possible)
| Item | State |
|---|---|
| FX ×79 | ✅ `fx_convert.convert_fx` — full FxEffectDef (header+292B elems+dyn tail). 46/46 raid pairs convert, 0 failures; diffs = float-LSB source divergence + inline-material −8/−16 class + 8 embedded-image cases (genuine console FX embed LOADED image pixels; we emit streamed refs — ipak carries pixels; acceptable for boot #1) |
| SndBank ×1 | ✅ byte-copy (`smalls_convert.convert_sndbank`) — 49.7 MB emits on skate |
| Techsets ×245 | ✅ was already wired; FIXED the on-the-fly manifest path (raid used `translate()['map']` which doesn't exist → now `emit_manifest()`), raid 224 subst + 3 exact |
| XAnim + smalls | ✅ `smalls_convert.py`: XAnimParts, DestructibleDef, PhysPreset, GfxLightDef, Glasses, SkinnedVertsDef (console = 24B body w/ 4 extra FOLLOW words + trailing u32 — fixed vs genuine 41B), + FxImpactTable via P2C.SIMPLE |
| GfxWorld ×1 | ⏸ stays Track F (generators session) — only remaining MISSING row |
| Two-pass assemble | ✅ `assemble_zone` is now two-pass: pass 1 builds the full omap, pass 2 re-emits so FORWARD alias refs resolve; PCConverter got `ext_reloc` fallback into the shared omap; omap gained FINE (exact) sub-regions from `PCConverter._reg` |
| Raid gate harness | ✅ `native_linker/raid_oracle_control.py` — console per-asset span walk (now walks ALL 889: skips aliased-header assets, handles the type-47 'MAP_ENTS' entry whose body is really Glasses — see OAT ContentLoaderT6 note: raw 47 = GLASSES, the MAP_ENTS-relocation rule was a myth), then per-asset byte-diff with SEMANTIC pointer comparison + allowlist |

mp_skate end-state: **112.2 MB emitted, every type except GfxWorld**. Raid: everything
emits; gate result `exact=105, ptr-equivalent=1, allowlisted=735, VIOLATION=38`.

## THE WALL — pointer values need the loader's allocation model (not stream offsets)
Proof (mp_raid genuine, StringTable configstrings):
- All 7009 intra-asset string-dedup aliases point at `source_stream_offset − 53`, i.e.
  the linker wrote **runtime addresses**: 53 stream bytes before the strings region do
  not consume block-5 space (temp-block data: asset header structs / names per ZoneCode
  `set block XFILE_BLOCK_TEMP`).
- The drift is NOT one constant: aliases targeting the cells array sit at a different
  phase (≡2 mod 8) than the strings (53 ≡ 5 mod 8) → per-region block/alignment effects.
- OAT's instrumented loader spells out the model: **asset roots align to 4 in block 5**;
  `ZoneLoaderFactoryT6` defines `XFILE_BLOCK_TEMP` as a real BLOCK_TYPE_TEMP; per-`Load<T>`
  alignment. Hooks already exist: `OAT_LOAD_OFFSET_LOG` (loader) / `OAT_WRITE_OFFSET_LOG`.

### Fix architecture (agreed shape, next session's core task)
Keep the converters untouched. Split pointer emission into two stages:
1. omap (exists): PC target b5 → OUR emitted stream position (fine+coarse map).
2. NEW `loader simulation` post-pass: walk OUR emitted zone with the console ZoneCode
   walker (walker.py + Layout(console=True) + `zc.default_block` + per-type alignment),
   maintaining per-block runtime cursors exactly like `InMemoryZoneOutputStream` /
   the generated T6 loaders (temp vs virtual, align-before-alloc). This yields
   stream_pos → (block, runtime_off); rewrite every emitted alias through it and encode
   with `zone_stream.encode_ptr`.
Calibrate stage 2 against genuine raid: simulate over the GENUINE zone and check the
simulated addresses reproduce the genuine alias values (the 7009-string dataset above is
the unit test). Only then apply to our emitted zone.

## Remaining per-type violations (sizes/content, raid gate) — chase list
- **ScriptParseTree ×13**: console GSC = PC GSC endian-swapped (verified on the saved
  pair `wiiu_ref/gsc_pair_*_mp_raid_fx.bin`: same length, header words + offset tables
  byte-swapped, code region mostly equal). Needs a GSC-aware BE swapper. Bounded.
- **GameWorldMp**: genuine console body 308076 vs our 241860 (+66 KB) — console PathData
  has extra/бigger sections; the WORLD identical-layout assumption fails here. Needs a
  gameworldmp probe comparison PC↔console.
- **clipMap_t**: sizes near-match (2238640 vs 2238630) but big hard-diff count —
  interior reorder/padding; needs region-level diff (same method as GfxWorld regions).
- **Glasses**: ours 9654 vs genuine 9622 — inline materials inside GlassDef carry the
  material −16/−32 class (likely allowlist once material class applied to nested).
- **DestructibleDef ×8**: 1–6 hard bytes each at ~@1639 — probably a u16 scriptstring
  or LSB float divergence; verify then allowlist or fix.
- **XAnimParts ×2 / RawFile ×1 / ComWorld(3 ptrs) / FxImpactTable(ptrs only) /
  KVP(ptr-equivalent ✓)**: mostly pointer-model artifacts; re-judge after stage-2 fix.
- **SkinnedVertsDef**: structure now matches genuine (24B body + trail); re-check.
- `no-console-pair ×2`: PC-only trailing techset + material — likely console aliased
  versions; verify pairing rule.

## Facts to keep (hard-won, do not re-derive)
- Console span walk of genuine zones MUST skip aliased-header assets (headerPtr !=
  FOLLOW ⇒ no body bytes) — `wiiu_zone.ZoneReader` doesn't expose headerPtr; read it at
  `assets_off + i*8 + 4`.
- Genuine raid tail: asset 850 TECHNIQUE_SET is aliased; the type-47 entry at 851 is the
  REAL Glasses inline body (`_console_glasses_end` in raid_oracle_control walks it).
- PC↔console genuine data diverges at float-LSB level in FX (and material hashIndex ×9);
  these are source-data divergence, NOT converter bugs — allowlist classes.
- Genuine console FX with inline materials: −8 per material (104 vs 112) plus, for 8 raid
  FX, embedded LOADED image pixel blocks (8–180 KB) — we emit streamed refs instead.
- omap stats after two-pass on raid: unresolved 2232 = refs into GfxWorld (not emitted)
  + pointer classes pending the loader-sim fix. The `unresolved=0 fatal` bar comes after
  stage-2 + GfxWorld.

## Definition of done (unchanged)
Raid gate PASS (only allowlisted diffs, semantic-pointer-correct), unresolved=0 fatal,
mp_skate assembles complete, round-trips, packs to `mp_skate_wiiu.ff` + ipak for Cemu.
