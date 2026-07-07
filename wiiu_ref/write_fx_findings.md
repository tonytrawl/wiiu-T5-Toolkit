# Write-path self-load FX fault (asset 183): root cause + fix (2026-07-05)

Session deliverable. Do not merge into WIIU_UNLINK_STATUS.md automatically. Style: plain, factual,
no em dashes.

## Headline

FIXED, and better than the target: the PC->console written mp_raid now **self-loads to completion,
3096/3096 asset records, exit 0, 0 warnings, 0 errors** (was: 182 assets then a segfault at the first
FX). Two independent bugs, both in the writer, neither in the FX layout:

1. The console TEMP->VIRTUAL block redirect destroyed the LOGICAL TEMP identity of asset pointers, so
   the writer emitted FOLLOWING sentinels and data-offset reuse aliases that the reader can never
   resolve. The first consumer of a cross-asset alias is the first FX (its FxElemVisuals reference
   earlier materials/models), hence the fault location.
2. The writer's PC->console asset-type remap still carried the "MAP_ENTS -> 47" myth that section 0v
   already disproved on the read side, so written MAP_ENTS came back as GLASSES on self-read.

Guards all green after the fix: PC mp_raid --list 0 warnings 0 errors; genuine common_mp 121; genuine
mp_raid 853; PC (non-WiiU) rewrite 0 errors.

## Bisection (how it was found)

- Reproduced: `OAT_REWRITE=1 OAT_WRITE_WIIU=1 OAT_WIIU_BLOCKREMAP=1 --list <pc mp_raid>` ->
  `ff_pack.pack_ff` -> `OAT_IGNORE_SIG=1 OAT_ALIAS_NULL=1 --list` = 182 assets, segfault at 183
  (type 33 FX).
- All 46 FX bodies in the written zone parse BYTE-EXACT with `fx_probe.py` (full dynamic walk,
  0 failures), so the emitted FX layout was correct and the fault had to be reader-state.
- Instrumented the generated FX loader (function-entry prints, regen-disposable): the crash is inside
  `Load_FxElemVisuals` for the first visual, i.e. dispatching a Material/XModel reference.
- `OAT_DBG_ALIAS` on the self-read showed the smoking gun: **aliasTbl = 0** (the reader recorded ZERO
  insert-alias entries over the whole zone; a genuine read records them), plus alias MISSes and a
  type-confused `HIT(ptr)` right at the FX. The FX visuals alias earlier assets; nothing those aliases
  point at was ever registered.
- Added `vpos` (current block offset) to the gated `OAT_DBG_WR` per-asset write trace and diffed the
  writer's per-asset offsets against the reader's `VIRTUAL_pos` trace: **zero cursor drift across all
  assets**. So block accounting was fine; the problem was purely pointer/alias semantics.
- After fixing bug 1, self-load reached 3043 assets and died with a clean VIRTUAL overflow at a
  TYPE mismatch: writer emitted PC 16 (MAP_ENTS) as raw 47, the (0v-fixed) reader decoded raw 47 as
  GLASSES (46) and mis-walked it. That exposed bug 2.

## Bug 1: logical TEMP identity lost by the console block redirect

Byte-level cause. In the fastfile format, TEMP-class (asset) pointers use the INSERT sentinel
(0xFFFFFFFE): the loader allocates a pointer-sized slot in the insert (VIRTUAL) block, registers it in
its alias table, and later reuse aliases point at that slot. The writer implements this with
`MarkFollowing` choosing insert-vs-following by "current block is TEMP" and `ReusableAddOffset`
allocating an insert slot when in TEMP.

On the console target, the TEMP->VIRTUAL redirect happened in two places BEFORE those decisions:
- codegen-level: `PushBlock(SwapEndianness() ? VIRTUAL : TEMP)` in the generated Write/WritePtr
  methods, and
- runtime-level: `OAT_WIIU_BLOCKREMAP` remapping inside `PushBlock`.
Either way the stream saw VIRTUAL, so every temp-asset pointer was emitted as FOLLOWING (fine for the
first, inline occurrence, which is why 182 assets loaded) and every reuse alias was emitted as a raw
DATA offset (`GetCurrentZonePointer`), which the reader has no registration for. On an x64 host those
data offsets cannot resolve natively either (host structs are wider than zone structs), which is
exactly the task-#26 artifact class, self-inflicted.

Fix (`ZoneOutputStream.cpp` + `ZoneWriteTemplate.cpp`):
- `InMemoryZoneOutputStream` now tracks a parallel stack of LOGICAL block types. `PushBlock` records
  the requested block's type before applying the console redirect (the redirect itself is now
  unconditional under swapEndianness; `OAT_WIIU_BLOCKREMAP` no longer needs to be set but is
  harmless).
- `MarkFollowing` and `ReusableAddOffset` consult `InLogicalTempBlock()` instead of the physical top
  block, so temp-class pointers get INSERT sentinels and insert-slot reuse registration again, exactly
  like the PC write path (where logical == physical made this work by accident).
- The two codegen-level `SwapEndianness() ? VIRTUAL : TEMP` pushes were reverted to plain TEMP pushes;
  the stream now owns the redirect and keeps the logical identity.
- Supporting reader symmetry already existed: `InsertPointerAliasLookup` allocates the identical
  4-byte slot in the reader's insert block per INSERT marker, so writer and reader block cursors stay
  in lockstep (verified: zero per-asset offset drift after the fix, and the reader's alias table is
  populated on self-read).

## Bug 2: writer-side asset-type remap was not the inverse of the reader

The writer had `t==16 -> 47; t>=43 -> +2; t>=7 -> +1`. Section 0v ground truth: raw 47 = GLASSES,
"MAP_ENTS at 47" is a myth. The reader (fixed in 0v) keeps a deliberate guard-protecting compromise
(second console insert modeled at 44 instead of the true 48), so the writer now implements the EXACT
INVERSE of the reader as-is:

| PC id | console id written |
|---|---|
| 0..6 | unchanged |
| 7..42 (incl. MAP_ENTS 16 -> 17) | +1 |
| 43 (LEADERBOARD) | 45 |
| 44 (XGLOBALS) | 46 |
| 45 (DDL) | no exact preimage under the reader compromise; warned if seen (absent from map zones) |
| 46 (GLASSES) | 47 |
| >= 47 | +2 |

Round-trip identity write(read) verified for every type present in mp_raid (histogram: 1,2,3,4,5,6,7,
8,9,12,13,15,16,17,18,33,34,41,42,46,48,49,54,57). The DDL hole and the 44-vs-48 compromise should be
resolved together with the raw-48 console-insert read handler (the flagged follow-up in 0v).

## Validation

- Self-load: 3096/3096 asset records, exit 0, "Finished with 0 warnings, 0 errors". This is past the
  original target (183) and past the glasses/clipMap items too, because the written zone's GLASSES is
  the consistently-remapped PC-shaped asset, not the genuine console layout.
- Content re-validated on the final output (identical to the previous session's results):
  46/46 FX bodies parse byte-exact; 111 models matched to genuine mp_raid, 464 shared surfaces with
  verts1 byte-exact and verts0 exact in position/binormal/pad (normals/tangents within the expected
  0p quantization); siege-skin tail parses at 11085 bytes.
- Guards: PC mp_raid 0/0; genuine common_mp 121; genuine mp_raid 853; PC rewrite 0/0.
- CAUTION for future validation scripts: a plain `OAT_REWRITE=1` (PC) run in the same directory
  overwrites `mp_raid_rewrite.ff` with the PC-format zone; regenerate the console file before
  probing it (this bit this session once).

## Genuine-format parity note (deliberate, documented divergence)

Genuine zones (PC and Wii U alike) emit interior asset data with FOLLOW and rely on slot-table
aliasing (the loader registers every reusable pointer FIELD; aliases point at the first referencing
slot; the reader resolves via its recorded-slot table). Retail zones therefore contain almost no
INSERT sentinels (genuine mp_raid: reader records only ~27 insert-alias entries but ~58k pointer-slot
registrations). OAT's writer has always used the INSERT/insert-slot mechanism for temp assets on PC;
this fix extends the same mechanism to the console target rather than reimplementing retail's
slot-based aliasing. Consequences:
- The written zone is format-legal (INSERT is a first-class fastfile pointer opcode on all platforms)
  and OAT self-loads it cleanly, but it is not byte-identical in STYLE to a retail-linked zone:
  temp-asset markers are 0xFFFFFFFE where retail has 0xFFFFFFFF, and reuse aliases point at insert
  slots instead of first-reference fields. The probes' FOLLOW-only matchers need INSERT added to
  their marker sets (or a normalization pass) when run against OAT-written zones.
- Console-engine risk is judged low (the engine implements the insert opcode; the insert-block
  allocations are accounted in the declared block sizes), but it is the first thing to suspect if a
  hardware boot fails at DB load with this zone. The retail-parity alternative (slot-based aliasing)
  is a bounded writer redesign: record the written offset of the first REFERENCING slot in
  ReusableAddOffset instead of allocating an insert slot.

## Files touched

- src/ZoneWriting/Zone/Stream/ZoneOutputStream.cpp (logical block-type stack; InLogicalTempBlock;
  MarkFollowing/ReusableAddOffset use logical type; TEMP redirect unconditional under swap)
- src/ZoneCodeGeneratorLib/Generating/Templates/ZoneWriteTemplate.cpp (reverted the two
  swap-conditional TEMP pushes to plain pushes)
- src/ZoneWriting/Game/T6/ContentWriterT6.cpp (corrected PC->console type remap = exact inverse of
  ContentLoaderT6; `vpos` added to the gated OAT_DBG_WR trace)
- Full regen (T6.log deleted); FX-loader instrumentation was in generated files and is gone.
