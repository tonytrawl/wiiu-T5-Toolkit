# Handoff: solve the map-zone console read — task #28 (SOLVE phase)

**Task:** derive the remaining console (Wii U) layout/format rules needed to fully unlink a genuine Wii U
**map** zone, in priority order: (1) the **stream-padding rule** that currently blocks `mp_raid` at the
StringTable, then (2) the console layouts for the **DLC-critical geometry/world assets** — `XModel`
(+`XSurface`/`XModelSurfs`), `GfxWorld`, `clipMap_t`, and any early map-zone assets that surface. This is
SOLVE only (pure Python triangulation against genuine zones, **no OAT/C++ build** — implementation happens
in the other session). Deliver byte-tables + verified rules.

Working directory: `C:\Users\Tony - Main Rig\Downloads\Testing enviroment`.

## Read first, in order
1. `WIIU_UNLINK_STATUS.md` §0j (this task's diagnosis), §0f/§0g (the solved GfxImage/GX2-shader layouts —
   your template), §0h (the reused-memory alias resolution).
2. `ROADMAP_DLC_PORT.md` — where this fits (Stage 1 unlink; XModel/GfxWorld/clipMap are the geometry/world
   the DLC actually needs).
3. `wiiu_ref/walker.py` (native graph walker — **byte-exact on simple assets**, resyncs-by-search on
   complex ones), `wiiu_ref/wiiu_zone.py` (asset-list reader), `wiiu_ref/struct_layout.py` (PC struct
   layouts from `T6_Assets.h`; `Layout(HDR, console=True)` drops ID3D11 `void*` fields).
4. `wiiu_ref/gfximage_probe.py` and `wiiu_ref/shader_probe.py` — the two triangulation tools that solved
   the previous layers. **Copy their method.**

## Context you must NOT re-derive (already done and verified)
- 360 & Wii U are 32-bit big-endian consoles sharing the asset enum; console divergences vs the PC struct
  are: dropped ID3D11 fields, array-count changes, `CONSOLE_MAX_ALIGN=4`, member-reorder-in-memory-order,
  and — for GPU assets — **whole different structs** (GX2). All handled in the x64 OAT fill path.
- **Solved console layouts:** Material (104 B), GfxImage (328 B GX2), MaterialTechniqueSet + GX2 vertex/
  pixel shaders, MaterialVertexDeclaration (92 B). `common_mp` reads **121 assets**.
- **Reused-memory / forward / empty-DELAY-block references** are resolved to null (asset-refs) or a zeroed
  buffer (data-ptrs) via `OAT_ALIAS_NULL` — that's a runtime flag, not layout; don't re-solve it.
- **The anomalous console Glasses is fixed:** its asset-list `header.data` is a non-FOLLOW value
  (`0xe1af0513`) yet a 16-byte inline stub follows (name FOLLOW/numGlasses/glasses FOLLOW/+12, none
  followed). Already handled. mp_raid asset order: KeyValuePairs, Glasses, SkinnedVerts, StringTable,
  then TechniqueSets…

## Sub-task A (blocker) — the stream-padding rule
On console, some asset bodies have **stream padding** before them that OAT (tightly-packed) doesn't
consume. Concrete case in `mp_raid_genuine.zone`: `SkinnedVerts` = body(8) + name `"skinnedverts\0"`(13)
= 21 stream bytes, ending at **file 0x5286**; but the genuine `StringTable` body starts at **file 0x528a**
— **4 zero bytes of padding** in between. OAT reads the StringTable 4 bytes early → `columnCount=-1` →
huge `cols*rows` alloc → crash.

Key facts you have:
- `assets_end` (first body) = 0x51d0. KVP@0x51d0 (145 B) → Glasses stub@0x5261 (16 B) → SkinnedVerts@0x5271
  (21 B, ends 0x5286) → **4 pad bytes** → StringTable@0x528a.
- 0x528a is **not** 4/8/16-aligned, so it is not simple absolute-offset alignment. The distinction that
  matters: OAT's *block cursor* gets aligned (a block-only bump) but the *stream* is tightly packed — yet
  the genuine console stream has real padding bytes. Figure out what rule produces them.

**Method:** the native walker is byte-exact for simple assets and records a `GAP` at each transition
(`walker.py` prints `next@0x… GAP=N`). Enumerate the gaps between **consecutive byte-exact assets** across
mp_raid (and zm_transit_original.zone), and correlate the gap size with: the next asset's struct
alignment, the previous asset's end offset (mod 2/4/8/16), the block vs stream offset, etc. Derive the
rule (e.g. "each asset body is stream-aligned to N", or "aligned relative to the VIRTUAL block base", or
"only structs with alignment ≥ K are padded"). Verify it predicts every gap.

## Sub-task B — console layouts for the geometry/world assets
Once the stream-padding rule is known, the read reaches the GPU/geometry tier. Derive console layouts
(byte-tables like §0f), each **verified byte-exact against the genuine zone**, for:
1. **StringTable** — likely same as PC (20 B: name, columnCount, rowCount, values, cellIndex; StringTableCell
   = 8 B). Confirm no divergence; the blocker there is Sub-task A, not the struct.
2. **XModel** + **XSurface**/**XModelSurfs** — the DLC geometry. Prior findings to build on: console
   `XSurface` = 64 B (drops the ID3D11 vb0/indexBuffer), vertices = **24-byte stride, big-endian float32
   xyz** (positions verified ~95%), triangles = BE u16. The vertex/index blobs are **GX2/Latte** (like the
   GX2Texture/shader work) — expect a *different* struct, not just shifted offsets. `wiiu_ref/extract_surf.py`,
   `probe_xsurface.py`, `wiiu_xmodel_extract.py` are starting points.
3. **GfxWorld** — the world/BSP (cells, portals, surfaces, light grid, static models). The largest T6
   struct; expect many sub-structs and some GX2-specific parts. Triangulate incrementally.
4. **clipMap_t** — collision (brushes, planes, nodes, leaves). Geometry-ish, largely
   platform-independent; derive by the same body-then-name/aliased-arrays method.

## Deliverable
For each: a byte-table (offsets, field, LE-vs-BE, which fields are dropped/added vs PC, array counts, the
per-item stream-consumption formula, and how sub-arrays/aliases are followed), plus the stream-padding
rule, written into `WIIU_UNLINK_STATUS.md` §0j and the `wiiu-native-unlinker` memory file. Save a genuine
sample `.bin` per struct and a probe script (`wiiu_ref/*_probe.py`) as the reference parser, like
`gfximage_probe.py`/`shader_probe.py`.

## Success criteria
- The stream-padding rule predicts every gap between byte-exact assets in mp_raid **and** zm_transit.
- Each geometry/world layout resyncs perfectly (body + dynamics land exactly on the next asset) across
  many samples in `mp_raid_genuine.zone` / `zm_transit_original.zone`.
- Sanity: XSurface vertex counts × 24 match the vertex-blob size; clipMap brush/plane counts are sane;
  GfxWorld cell/surface counts are sane.

## Don't chase
- Don't touch the solved layouts (Material/GfxImage/techset/Glasses) or the alias resolution.
- No OAT/C++ build — Python only, so it won't collide with the main (implementing) session that owns
  `tools/ref_oat/build`.
- The MENULIST/menuDef tail (task #27) and full common_mp are non-DLC-critical — ignore.

When you deliver the stream-padding rule + geometry byte-tables, the main session implements them
(codegen hooks / hand-written console readers, mirroring the GfxImage & GX2-shader implementations).
