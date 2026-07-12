# HANDOFF — ASSEMBLE session: loader-simulation pointer pass (THE critical-path item)

Continuation of `HANDOFF_assemble_pointer_model.md` (read it first — it holds the proof, the
repro dataset, and the fix architecture; do not re-derive any of its "Facts to keep").
You own `native_linker/produce_nobackbone.py` + `raid_oracle_control.py`.

## The task in one line
Build the **loader-simulation post-pass**: map every emitted stream position to the console
loader's RUNTIME (block, offset) address and rewrite all alias pointer values through that map —
then flip the raid gate to PASS.

## Why (recap)
Genuine zones encode runtime allocation addresses, not stream offsets: temp-block data (asset
headers/names, `XFILE_BLOCK_TEMP`) consumes no block-5 space, asset roots align to 4, and each
`Load<T>` aligns before alloc. Proven: 7009 StringTable dedup aliases in genuine raid all sit at
stream−53; different regions sit at different mod-8 phases. Our stream-linear omap therefore
emits wrong pointer VALUES zone-wide (gate: `VIOLATION=38`, plus pointer classes inside
allowlisted assets).

## Build order
1. **Simulator core.** Walk a zone with the console ZoneCode walker (`walker.py`,
   `Layout(console=True)`), maintaining per-block runtime cursors exactly like OAT's
   `InMemoryZoneOutputStream` / generated T6 loaders: `zc.default_block` per type, temp vs
   virtual blocks, align-before-alloc, asset roots align-4. Output: `stream_pos → (block,
   runtime_off)`. Use `OAT_LOAD_OFFSET_LOG` / `OAT_WRITE_OFFSET_LOG` hooks to settle any
   ambiguity empirically — don't guess alignment rules.
2. **CALIBRATION GATE — ≥2 genuine MP zones + 1 ZM zone before touching our output.**
   Run the simulator over GENUINE raid, GENUINE nuketown (and dockside if cheap), and one ZM
   zone (zm_nuked or zm_transit): the simulated addresses must reproduce the genuine alias
   values. The 7009-string raid dataset is the first unit test, but **raid alone does NOT
   validate the model** (house rule: raid is repeatedly the degenerate case — alignment phases
   differ per region, so a second map with different sizes/phases is the real test). Record
   per-map reproduction stats in the doc.
3. **Apply to our emitted zone.** Two-stage pointer emission: existing omap (PC b5 → our stream
   pos) → simulator (our stream pos → runtime addr) → `zone_stream.encode_ptr`. Converters stay
   untouched.
4. **Re-run the raid gate.** Expect the pointer-artifact violations (XAnimParts ×2, RawFile,
   ComWorld ptrs, FxImpactTable ptrs, KVP) to re-judge clean. Target: only allowlisted diffs.
5. **unresolved → 0, then FATAL.** Current 2232 = GfxWorld refs (Track F, expected) + pointer
   classes (this fix). After stage 3, everything non-GfxWorld must resolve; keep GfxWorld refs
   explicitly tagged until Track F delivers, then arm the fatal assert.

## Also verify while you're in the asset list (cheap, doc-truth item)
The gate work found raw type 47 = GLASSES and the "MAP_ENTS relocation rule" was a myth.
**Confirm what the MP console-only insert set actually is** (asset-list level: is there a real
MAP_ENTS entry? what is the duplicate SOUND?) against ≥2 genuine MP zones, and report — the
standing "MP inserts = MAP_ENTS + SOUND" claim in PROJECT_STATE/memory must be corrected or
re-confirmed by the main session.

## Out of scope (parallel session owns these — do NOT edit their files)
GSC endian-swapper + GameWorldMp +66 KB probe + clipMap interior diff →
`HANDOFF_chase_content_gaps.md`. That session works in NEW files and hands you converters to
integrate; you stay the sole editor of `produce_nobackbone.py`, `pc_to_console.py`, omap code.
Track F still owns `gfxworld_*.py`.

## Constraints (standing)
Never write under `E:\`. struct_layout is WRONG for console sizes — trust probes/OAT hooks.
Self-consistency ≠ pointer correctness — the calibrated simulator + raid gate are the pointer
bar. Keep `PROJECT_STATE.md` + `CAVEATS_nobackbone_boot.md` truthful as you land pieces.

## Definition of done
Simulator reproduces genuine alias values on ≥2 MP zones (+1 ZM spot-check); our raid assemble
passes the gate with only allowlisted diffs and semantically-correct pointers; unresolved
count = GfxWorld-only (tagged) with the fatal assert ready; MP insert-set fact confirmed and
reported. Then the remaining path is: integrate chase-session converters → Track F GfxWorld →
pack/ipak/sig-patch → first mp_skate boot.
