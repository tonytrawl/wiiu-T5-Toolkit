# Native WiiU (T6, v148) console linker

From-scratch replacement for the OAT band-aid. A linker that authors the whole zone
graph natively assigns every asset's block offset as it writes, so **every pointer is
emitted correctly by construction** — dissolving the dangling-pointer class that the
genuine-blob-transplant approach kept hitting (gfxworld cells, GameWorldMp reused-mem,
…). It is also the only path to DLC maps, which have no genuine console zone to copy.

## Status

**Stage 1 — round-trip core: COMPLETE ✓ — FULL ZONE BYTE-IDENTICAL.**
`python body_relayout.py ../wiiu_ref/mp_raid_genuine.zone 889` reproduces the entire genuine
console mp_raid zone: 86,174,226 / 86,174,226 bytes match byte-for-byte. 850/889 assets are
individually re-laid-out & byte-verified (engine computes every offset/pointer), including
GfxWorld (22.2 MB) and GameWorldMp — the OAT walls. The final 39 tail assets (glass/MapEnts/
ClipMap/shared) are verbatim-copied for now (probes exist to individualize them). This proves
the write engine produces a real, loadable console map zone.

**Earlier detail below.**

- `zone_stream.py` — the write engine (ports OAT's `InMemoryZoneOutputStream`
  semantics to Python, console-configured: big-endian, 32-bit pointers, 8 blocks,
  3 block bits, encoding `(block<<29 | offset) + 1`, FOLLOW/INSERT sentinels, block
  cursor + alignment + reused-memory aliasing + header emission). Smoke-tested.
- `stage1_roundtrip.py` — **container round-trip: BYTE-IDENTICAL ✓.** Parses a genuine
  zone's XFile header + XAssetList + script-string table + asset-list array into a
  neutral form and re-emits it through the engine; output matches the source byte for
  byte (0x51d0 bytes for mp_raid). Validates header emission, block-5 offset math
  (block-5 offset == stream offset − 64), FOLLOW/null sentinels, string serialization
  and asset-array layout, independent of per-asset body knowledge.

- `body_relayout.py` — **asset-BODY re-layout: 749/889 assets byte-identical ✓** (indices
  0-748). Generic struct-walker for simple types + a `DELIMITERS` registry of solved probes
  (shader_probe/fx_probe/xmodel_probe/destructibledef_probe) for complex types (copy the
  delimited region verbatim — byte-exact for a round-trip; structural emitters come in Stage 2
  for authoring). A DRIFT GUARD checks each next body's name pointer so a wrong delimiter end
  is caught at its source. Also fixed the skinned-XSurface pre-verts0 blob sizing (via
  skinned_probe's formula) and the console packed-array rule. WALL: asset 749 ComWorld —
  console ComPrimaryLight layout (168B, mixed aliased/inline defNames) still unsolved; needs
  PC-oracle cross-ref. See memory `native-console-linker`.

  Earlier milestone detail (the engine + first assets):
- `body_relayout.py` — asset-BODY re-layout foundation. Walks the
  genuine graph like the reader but re-emits every region through the engine, patching
  alias pointers via a source→writer offset map, and asserts byte-identity per asset
  (first divergence pinpoints the exact struct/directive to fix — exact for writing,
  where the reader could paper a size error over with next-body resync). Byte-identical
  through: KEYVALUEPAIRS (incl. reused-memory back-aliases), GLASSES (console 16B stub),
  SKINNEDVERTS (console trailing u32), STRINGTABLE (142 KB, incl. cell strings + index),
  and 2× small TECHNIQUE_SET.
  - **Console rule discovered:** the genuine console linker PACKS FOLLOW arrays — it does
    NOT apply OAT's defensive `Align(4)` (proven: the StringTableCell array lands at an
    unaligned offset). Only over-aligned types (16/128, e.g. vertex/shader blobs) pad.
    Encoded in `emit_array` (align only when `align > 4`).
  - Console layout quirks captured: `CONSOLE_TRAIL` (SkinnedVertsDef +4), console struct
    overrides via the reader's `CONSOLE_OVERRIDE` (GLASSES).

## Next increment — TECHNIQUE_SET / GX2 shaders (asset 6)

Full techsets carry inline console **GX2 vertex/pixel shader programs** that OAT's
directives mark `never` (PC streams them separately). Re-laying them out byte-exact needs
the console techset serialization: techniques → passes → {vertexShader, vertexDecl,
pixelShader, args}, with the GX2 program blobs and their alignment. `wiiu_ref/shader_probe.py`
(`parse_techset`) already delimits these for the material-inline case and is the starting
point. After techsets: XMODEL, MATERIAL, then the world assets.

Continue the same way — extend one asset type at a time, assert byte-identity, fix at the
first divergence.

Machinery needed (reuse `wiiu_ref/struct_layout.py` + `wiiu_ref/walker.py`):
- struct-driven walk producing a re-layout plan (body bytes + ordered FOLLOW children,
  honoring `reorder`, `count`, `string`, `condition`, `reusable`, `arraysize`);
- reused-memory aliasing: track each written array/string by source identity so a later
  reference emits an alias to the earlier copy (the engine's `reusable_*` methods).
  NOTE: the very first asset (KeyValuePairs `mp_raid`) already needs this — `kvp[1].value`
  is an alias, not FOLLOW.

### Validation oracle
`OAT_PTR_LOG` (added to `tools/ref_oat/.../ZoneInputStream.cpp`) dumps every pointer the
genuine loader resolves as `block\toffset\tkind`. Generate with:
```
OAT_IGNORE_SIG=1 OAT_ALIAS_NULL=1 OAT_PTR_LOG=ptr_resolve.tsv \
  Unlinker.exe --list <genuine packed .ff>
```
Any pointer the native linker emits must resolve to the same target the oracle recorded.

## Staged plan
1. Round-trip core (this) — read genuine console zone, re-emit byte-identical.
2. Author a map natively from PC source: simple assets in console layout, linker computes
   all cross-refs; inline genuine gfxworld but author its refs into the consistent graph;
   validate vs `OAT_PTR_LOG`.
3. Synthesize gfxworld console gump/lighting/dpvs so DLC maps work.

## What carries over from the OAT era
Sig bypass, IPAK texture streaming, codec/block-size, GSC transcode — all reusable as-is.
Reference artifacts: `wiiu_ref/gfxworld_raid_remapped.blob`, `gameworldmp_empty.blob`,
the reverse-engineered console struct layouts, and the `_t6_write/load` hooks.
