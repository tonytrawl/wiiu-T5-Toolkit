# FINDINGS — Loader-simulation pointer model (Track G pointer pass) — 2026-07-09

The critical-path item from `HANDOFF_assemble_pointer_sim.md` is DONE: alias pointer values
are now emitted through a calibrated console-loader allocation model. This doc records the
model, the calibration evidence, and what remains.

## THE MODEL (calibrated, 4 console zones + 5 PC zones)
Alias pointer values encode the loader's RUNTIME block-5 allocation address, not stream
offsets. The runtime cursor is simulated from the stream with these rules:

1. **Temp roots**: each top-level asset's ROOT STRUCT bytes load into the reusable TEMP
   block — they consume NO block-5 space. Everything followed (names, arrays, strings,
   trailing words) is VIRTUAL and consumes 1:1.
   Console-true root sizes matter (`Material`=104, `SkinnedVertsDef`=24 incl. its 4 FF words).
2. **Per-allocation alignment**: every allocation aligns the runtime cursor to its type
   alignment (structs/u32 → 4, u16 → 2, char/strings → 1; SkinnedVerts trailing u32 → 4).
   The STREAM stays packed — alignment exists only in the runtime address space.
3. **XAsset array aligns to 8**: the asset array allocation is 8-aligned. This shifts the
   whole content base by `align8(assets_off-64) - (assets_off-64)` (raid/transit phase 0,
   dockside/la phase 5 → +3). This was the last ±4 residual.
4. **NO asset-root align-4** of the virtual cursor (falsified: shifts raid/dockside/transit
   by −4).
5. **Asset-handle refs are SLOT aliases**: references to (temp-rooted) assets encode
   `arr_base + idx*8 + 4` — the XAsset array entry's header-pointer slot (OAT's
   ConvertOffsetToAliasLookup keys on it). NOT the asset body address.
6. **PC zones (v147 LE) use the SAME model**: PC alias values are PC-runtime addresses
   (temp roots + alloc align + array align-8). Verified: PC raid KVP dedup alias 20956 =
   stream 20968 − 12-byte root; PC ST datasets reproduce exactly.

## Calibration results (StringTable dedup datasets, exact-value reproduction)
| zone | ok | outliers |
|---|---|---|
| mp_raid (console) | 7009 | 6 (suffix/hash-collision class, constant offset) |
| mp_dockside (console) | 9769 | 9 (same class) |
| mp_la (console) | 8654 | 8 |
| zm_transit (console) | 2821 | 0 |
| mp_raid (PC) | 7009 | 6 |
| mp_dockside (PC) | 9769 | 9 |
| mp_nuketown (PC) | 4837 | 3 |
| zm_nuked (PC) | 1624 | 0 |
| mp_skate (PC) | 4607 | 3 |

Outlier class: the console/PC linker dedups string SUFFIXES (e.g. mp_la KVP value alias =
'la' inside 'mp_la' at rel+3); the outliers are refs whose byhash pairing picked a
different source string. Not a model failure.

## Code
- `native_linker/loader_sim.py` — SimWriter/SimEmitter (console), PCSimEmitter (PC, LE),
  `simulate()` / `simulate_stream()` / `simulate_pc()`, `RuntimeMap`, `InverseMap`,
  `calibrate()` / `calibrate_pc()`.
- `native_linker/produce_nobackbone.py` — THREE-pass assemble: pass 1 sizes, pass 2 full
  linear map, pass 3 loader-sim runtime re-encode. Pointer chain:
  **PC alias (PC-runtime) → InverseMap → PC stream → omap fine/coarse → our stream →
  RuntimeMap → our runtime → encode**. Slot refs short-circuit to `our_arr + idx*8+4`.
  FATAL assert armed: unresolved must be attributable to GfxWorld (+ tagged oddballs).
- `native_linker/pc_to_console.py` — PCConverter.finalize gained `encode` (runtime
  encoder) + `pc_inv` (PC-runtime reverse) hooks.
- `native_linker/raid_oracle_control.py` — gate resolves pointers SEMANTICALLY in runtime
  space on both sides (asset identity = name + all-rows occurrence; slot refs = '#slot').

## Gate status after the pointer pass (raid)
- **ptr-eq (all pointers semantically correct)**: StringTable, KeyValuePairs, FxImpactTable.
- exact: PhysPreset ×3, SkinnedVertsDef, RawFile, FX ×97, techsets ×3.
- Former "pointer-artifact violations" (XAnimParts ×2, RawFile, SndBank, tail SPTs)
  reclassified: they sit in the **genuine-side walk desync zone** after clipMap (assets
  853–882) — the genuine console clipMap has **~2.4 MB of unwalked interior** (chase
  session's "clipMap interior diff"; `maps/mp/...gsc` content found at walked_end+2.44MB).
  Gate now quarantines those pairs as 'tail-unverifiable' until the clipMap walk closes.
- Remaining REAL violations = chase-session content items: ScriptParseTree ×5 (GSC endian),
  GameWorldMp (+66 KB), clipMap interior, Glasses (+32 = 2× material class + hard),
  DestructibleDef (float-LSB class + a small **geometry-share pointer class**: piece
  pointers targeting packed vertex data INSIDE XModels — both sides agree it's model
  geometry; needs the destructible/xmodel share map; ~220 pointers).
- ComWorld ptrbad=3 (small, undiagnosed).
- unresolved (raid): 802 = 797 GfxWorld (Track F, expected) + 5 tagged oddballs.
- unresolved (mp_skate): 8128 = 7555 GfxWorld + 573 'outside' — the 573 need a look
  (probably PC-walk span gaps on skate; they pass through tagged).

## MP console-only insert set — CONFIRMED on raid + dockside (asset-list level)
Console list = PC list + exactly TWO rows, identically on both MP zones:
1. **index 1: raw type 48, ALIASED** (no body). With raw 47 = GLASSES (proven: the raw-47
   FOLLOW row's body IS the map's Glasses), raw 48 = MAP_ENTS ⇒ the insert is an
   **aliased MAP_ENTS reference**, NOT an inline body. (The old "MAP_ENTS inline insert"
   claim is wrong; the mapEnts content lives inline in clipMap on both platforms.)
2. **one extra SOUND row with FOLLOW body** immediately after the main SOUND (second
   SndBank body; true size unverifiable until the clipMap walk gap closes — it sits in
   the desync zone).
PC's GLASSES row (type 46 FOLLOW) = console raw-47 row at the same relative position.

## Caveats / next
- Verbatim-walked types (XModel/Material/FX/techsets in the CONSOLE sim; complex types in
  the PC sim) have linear interior approximation — interior alignment points inside them
  are unmodeled. Interior cross-refs into them can drift by small align deltas.
- 'allow-ptrbad' counts inside allowlisted assets are NOT a metric — content-diff bytes
  (substituted techsets, skinned models) produce alias-looking float windows.
- Console sim walk breaks: dockside @758 CLIPMAP, la @968 techset, transit @496 techset,
  PC nuketown/zm_nuked @XMODEL — fine for calibration (ST early), fix for full-zone use.
- For the BOOT artifact the container must be authored and `our_arr` / content base set
  from the real container layout (currently synthetic arr@0, content@n*8; the gate is
  base-independent).
