# Offline RPL RE — vd0 per-surface offset (Thread A prep, 2026-07-06)

Disassembled `t6mp_cafef_rpl.rpl` (.text @0x02000000, 11.5 MB) with capstone to attack the
vd0 per-surface offset blocker WITHOUT Cemu. Results below reshape Thread A and kill several
dead-ends. Tooling: `python3` + `capstone` (installed), section reader in `wiiu_ref/rpl_sigpatch.py`
(`_sections`, `_sec_bytes`). Text section = index 1, vaddr 0x02000000.

## Confirmed from the GX2 log (retail Raid capture, log.txt)
`GX2SetAttribBuffer(index, size, stride, addr)`.
- 55 unique **stride-36** world pointers, all in `[0x3a9cc000, vd0_end=0x3aad2510)`. This is a
  **DPVS-visible subset** of the full ~5.86 MB worldVd (162,752 verts), NOT consecutive surfaces.
- **`size` arg = bytes-remaining (`vd0_end - addr`)**, NOT the surface vertex count. Many draws'
  `addr+size` land exactly on `vd0_end`. => do NOT use `size/36` as vertex count.
- All 55 pointers are **16-byte aligned**; 9 distinct residues mod 36 => the buffer is NOT a pure
  `firstVertex*36` packing. Per-surface blocks are **padded to 16 bytes**:
  `blockBytes = align16(vertexCount * 36)`, and `offset = running accumulation of those blocks`.
- Consistent model: `addr = worldVd_base + cursorOffset`, `size = vd0_end - addr`, indices
  0-relative, baseVertex=0. This is exactly what prior GPU capture said; firstVertex*36 was
  correctly ruled out because of the 16-align padding + console reorder.

## Loader / draw path (disassembled)
- **`Load_GfxWorldDraw` @0x02222fb8 is NOT the offset computer.** It's the generic DB
  pointer-registration jump-table (tiny helpers calling alloc `0x2233908` / stream-fixup
  `0x2222bb0`). Do not breakpoint here for the offset.
- **Draw-time attrib set is a cached-descriptor replay** at func `0x029613e0`:
  reads descriptor `r4`: `addr=[r4+0x24]`, `size=[r4+0x20]`, `stride=[r4+0x38]`, stores the
  attrib-decl ptr `r4+0xc` into `[gfxstate+0x98]`, then `GX2SetAttribBuffer(0,size,stride,addr)`.
  This is the GENERIC vertex-stream setter (world + models). Backtracing GX2SetAttribBuffer lands
  HERE — a dead-end; the offset was computed earlier and cached in the descriptor's +0x24.
- World draw index helper `0x0295f528`: `idxBase=[[gfxstate+0x98]+4]`,
  `idxPtr = idxBase + [params+8]*2` (baseIndex, u16), `count=[params+4]*3` (triCount*3).
  Tail-branches to `GX2DrawIndexedEx` trampoline `0x2b00d50`. Only 2 DrawIndexedEx sites total
  (`0x0295f558/58c`) = the world surface draw.
- `0x02961278` (reads `worldVd_base+cursor` from `[[0x123b3080+0x228]+0x80]+[+0x98]`, count
  `([+0x84]-[+0x98])>>6`) is a **debug/immediate colored-point draw** overlaying the buffer —
  RED HERRING, not the world surface path.

## The ONE remaining unknown (what Cemu must answer)
The per-surface **vertex-buffer descriptor builder** (writes `desc+0x24 = worldVd_base + offset`)
is dispatched **indirectly** (no direct `bl` callers found), reached per-surface from the
render-surf list. Need: **does the builder read the per-surface vertex count from a stored struct
field, or derive it by scanning the index range (unique verts)?**
- If DERIVED from indices => our converter is automatically self-consistent (we lay contiguous
  16-aligned blocks, 0-relative indices, in surface order; the console accumulator reproduces our
  offsets). Thread B is trivial.
- If READ from a field => we must write that field per surface. Need its struct offset.

`vertexCount@40` is 0 for ~99% of surfaces, so if it's field-read it is NOT that field.

## Symbols / addresses
- `GX2SetAttribBuffer` import stub 0xc096d5d0; 25 call sites (via relocs). `GX2DrawIndexedEx`
  0xc096cff8, 2 sites. `GX2SetFetchShader` 0xc096d698, 7 sites.
- Generic attrib-replay: `0x029613e0`. World draw+index: `0x0295f528`. R_LoadWorld `0x02957de0`.
- Renderer state global base seen: `0x123b3080` (`+0x228` -> a draw-state; +0x248/+0x24c/+0x24 c).

## ⭐ RESOLUTION (2026-07-06, live Cemu + genuine-zone validation) — SUPERSEDES above unknowns
Cemu runs the **installed** RPL (`mlc01\...\t6mp_cafef_rpl.rpl.orig`), NOT the loose
`wiiu_ref/t6mp_cafef_rpl.rpl`. Runtime addr = installed-file addr **+0x2000** (module base
0x02002000). Working copy saved as `wiiu_ref/_running.rpl`. Re-derived addresses in that build:
generic attrib-replay `0x029abd00` (+0x2000=**0x029ADD00**), world-only indexed-draw wrapper
`0x029a9e3c` (+0x2000=**0x029ABE3C**), R_LoadWorld `0x02957de0`.

**Live capture (world surface draw, r5 = per-surface GfxDrawSurf command, ~0x20B):**
`[r5+0]=vertexCount, [r5+4]=triCount, [r5+8]=baseIndex`, then 4 floats, then a ptr@+0x1c.
Descriptor is a reused scratch buffer; `[desc+0x24]=vertexPtr, +0x20=size, +0x38=stride(36 world/32 model)`.

**Genuine-zone validation (`wiiu_ref/mp_raid_genuine.zone`, 5281 surfaces, 162752 verts,
362316 indices):**
- `baseIndex` (@44 in GfxSurface) is **100% cumulative** (5280/5280) = running Σ(triCount*3).
  => shared index buffer, surfaces sequential, indices 0-relative to a per-surface VERTEX GROUP.
- **`vertexDataOffset0` (@12) IS the per-surface vd0 BYTE offset** (loader pointer =
  vd0_base + vertexDataOffset0). Surfaces sharing a vertexDataOffset0 share a vertex block; for
  clean vd0 groups, **max(index) == groupVerts-1, 45/45 strict, 0 violations**. So the offset is a
  **STORED FIELD**, not a runtime accumulator. (The old handoff "vertexDataOffset0 ruled out" was
  wrong — likely measured against PC-reordered data.)
- vd0 is ~tightly packed (162752*36≈5.86MB); NOT per-surface 16-padded. The earlier "16-byte
  align" reading was a sparse-GPU-capture artifact (undrawn surfaces between captured pointers).
- `vertexCount@40` is 0 for ~most surfaces (unreliable) — NOT needed: group vertex count =
  max(index)+1, derivable from the index range.

**Remaining cleanup:** two vertex streams exist — vd0 (36B, 5,860,976B) and vd1 (371,876B). Some
surfaces reference vd1 via vertexDataOffset1; mixing vd0/vd1 surfaces is why a naive all-surfaces
vertexDataOffset0 sort is non-monotonic and ~46 groups look "bad". Need the vd0-vs-vd1 selector
field in GfxSurface to separate them, then the rule validates 100% per stream.

**Converter (Thread B) implication:** it is NOT a mysterious loader accumulation. For each surface
write: `vertexDataOffset0` = byte offset of its vertex group in vd0; `baseIndex` = cumulative
Σ(triCount*3); indices 0-relative to the group; lay vd0 out group-order. If the converter already
keeps PC order self-consistently, the render bug is more likely in the 36B vertex FORMAT convert
(`conv_world_vertex`) or vd0 emission (`draw.vd0.data` is `reorder_pc`, may not apply the 36B
convert) than in the offset — re-examine that next.

## PC==console layout proof + vertex-format reality (the converter's real task)
Ran the identical validation on the PC oracle (`PC ff/mp_raid.zone`): **PC and console GfxWorld are
structurally IDENTICAL** — 5281 surfaces, 362316 indices, 5,860,976 B vd0, baseIndex 100% cumulative
on BOTH, same 126/46/454 group split. => **the console does NOT reorder surfaces/blocks vs PC.**
No reorder, no offset computation needed: convert vd0/indices/surfaces IN PLACE (PC order) and it is
self-consistent because vertexDataOffset0/baseIndex are stored fields identical on both sides.

Byte-compare of `conv_world_vertex(PC vd0)` vs genuine console vd0 = only **58.5%** match (docstring's
"32/36 byte-exact" is optimistic). Per-field diff pattern:
- pos/uv (+0..15,+24..31): ~78% match — the ~22% diff = console **within-block GX2 vertex-cache
  reorder** (indices remapped to match). IRRELEVANT to correctness: keep PC order for vd0 AND its
  indices together and it renders fine (baseVertex=0, 0-relative indices).
- color/normal/tangent (+16..23,+32..35): ~80% DIFFER — console **re-encodes** these (baked vertex
  lighting). Cosmetic, not geometry. conv_world_vertex's color(byte-copy)/normal/tangent handling is
  NOT what console stores; keeping PC values renders geometry correctly with PC-ish lighting.

## Converter gap (Thread B — concrete, not yet done)
`gfxworld_assemble.py::convert_region` returns None for `reorder_pc`/`surface`, so vd0/indices/
surfaces currently **reuse the genuine Raid baseline** — geometry only works as a genuine-Raid
null-test; a new map (dust2) converts NOTHING here. To implement:
1. `draw.vd.data` (vd0, the LARGE span): apply `conv_world_vertex` (keep PC order).
   NOTE key collision: `_key` maps both `draw.vd0.data` and `draw.vd1.data` to `draw.vd.data`
   (digits stripped) — dispatch by span size (vd0=5,860,976; vd1=371,876) or span order. vd1 has a
   DIFFERENT vertex format (371876/36 not integer) — needs its own converter (TODO).
2. `draw.indices`: `swap2` (u16 endian), keep PC order.
3. `dpvs.surfaces` (80B): field-aware swap preserving vertexDataOffset0@12/firstVertex@32/
   vertexCount@40(u16)/triCount@42(u16)/baseIndex@44(u32) + relocate material ptr@48. (Implement the
   `surface` method in convert_region.)
Because PC order is kept throughout, the result is self-consistent → renders. Test: build ff, Cemu.

## Step-1 wiring landed + material-ptr reloc + vd1 triage (2026-07-06 cont.)
(a) **Material-pointer relocation DONE.** `conv_surface(pc_bytes, stride=80, reloc=None)` now handles
`material@48` via the pipeline's `reloc(pc_ptr)->console_ptr` convention (sentinels FOLLOW/INSERT/
null preserved verbatim; else reloc then BE-pack), identical to material_convert/xmodel_convert/
fx_convert. Identity default for the oracle (material word = expected per-surface divergence); a real
map MUST pass the omap-backed reloc or the surface points at a dangling PC alias -> loader crash.
Oracle unchanged: surfaces 69.20% (all = PC-zero mins/maxs + material ptr, no wiring bug).

Assembler wiring verified (Raid oracle): coverage 0%->47%. All deterministic regions 100%.
draw.indices 97.30% (within-block reorder). draw.vd0 58.56% (baked lighting + reorder, by design).
vd1 explicitly [!!] UNCONVERTED (not masked).

(b) **vd1 triage — mp_skate USES vd1; format RE required before build.** Target pivoted from dust2
(community port) to mp_skate (retail PC-only DLC map, no console backbone). Decrypted
`mp_skate.ff`->`mp_skate_pc.zone` (163 MB) via `tools/ff_decrypt.py` (PC Salsa20+zlib). OAT
`Unlinker.exe --list mp_skate.ff` parses its `gfxworld` with **0 errors** using the T6 struct that
contains GfxWorldVertexData1. Exact mp_skate vd1 byte count NOT pinned (multi-block streamed format
+ PC walker drifts at asset 632 XMODEL; OAT STREAM_pos is a different zone block than body offsets)
— but not needed: mp_raid (retail) vd1 = 371,876 B confirms retail maps populate vd1, and a
no-backbone map cannot reuse-genuine, so vd1 is MANDATORY.

**vd1 nature (from OAT write_db):** both vd0 and vd1 are `{ byte* data; GfxWorldVertexBuffer vb }`
written as an OPAQUE raw blob — `Write<byte128>(vd.data, vertexDataSize{0,1})`, 128-aligned. The
per-vertex internal format is NOT in the struct code (it's a GPU buffer, like vd0's 36B was). So vd1
needs its own stride/field reversal (separate RE task, same class as the vd0 36B work). vd1 stride
unknown; mp_raid vd1=371,876 B is not vertexCount*any-clean-stride vs 162,752 verts -> vd1 likely a
different element set (secondary lightmap/attribute stream). NEXT: reverse vd1 stride/fields.

## vd1 SOLVED (2026-07-06) — it was trivial, not deep RE
T6 `GfxWorldVertexData1 = {byte128* data; void* vb}` has NO count/stride field (pure opaque blob,
sized by GfxWorldDraw.vertexDataSize1). But stride is recoverable from surface metadata: every
genuine `vertexDataOffset1@28` is divisible by 4 and NOT by 8 (e.g. 172) -> **vd1 stride = 4 B/vert
= 2x u16 (likely f16 lightmap UVs).** Byte compare console vs PC vd1 elements = **swap2** (each
2-byte half byte-swapped): e.g. console `bc353afd` = PC `35bcfd3a` with each u16 reversed.
=> vd1 converter = `swap_n(bytes, 2)`. Wired in gfxworld_assemble (2nd 'draw.vd.data' span routes to
swap2). Oracle match **94.09%** (residual = within-block reorder, same as vd0/indices). Surfaces'
`vertexDataOffset1@28` is already swapped by conv_surface (in its SW4 list). vd1 no longer a blocker.

## Full step-1 pipeline state (Raid oracle, coverage 48%)
vd0 58.56% (baked lighting+reorder) | vd1 94.09% (swap2) | indices 97.30% | surfaces 69.20%
(PC-zero mins/maxs + material ptr). ALL residuals explained, all self-consistent in PC order.
Remaining before a real mp_skate build: (1) no-backbone assemble path (locate+read mp_skate GfxWorld
— native walker drifts @asset632; use OAT front-end, see block-addr mapping caveat), (2) real omap
reloc for mp_skate materials. Highest-info next test: build mp_raid with PC-CONVERTED geometry
(not baseline-reused) and Cemu-load — validates the geometry pipeline end-to-end on hardware using
the map we can already fully build (validation-ladder step 3).

## MAJOR CORRECTION (2026-07-06): vd0 is per-GROUP padded; flat conv was the warp bug
Build #1 (converted geometry + genuine surfaces) rendered WARPED on hardware. Root cause found and
it invalidates several earlier claims in THIS doc:
- **vd0 is NOT a flat 36B array.** Each surface vertex group = vertexCount*36 bytes then PADDED to
  a 16-byte boundary. (vertexDataOffset0 deltas are NOT 36-multiples, e.g. group 432->1552 = 1120 =
  align16(31*36).) My original 16-byte-align finding was RIGHT; dismissing it as a sparse-capture
  artifact was wrong.
- A FLAT 36-stride conv drifts out of alignment after the first padded group and corrupts every
  later group -> the warp. Reading vd0 flat also produced garbage floats past vert ~43, which I
  MISread as "heavy reorder" and "baked-lighting re-encode." **Both were flat-drift artifacts.**
- **GROUP-AWARE truth:** convert each group's vertexCount verts at vertexDataOffset0 (skip padding).
  Result: PC vd0 positions match genuine **100% (162752/162752, 394/394 groups)**; full vertex
  **32/36 byte-exact** (only the 4 tangent bytes differ = cosmetic packed repack). NO reorder, NO
  baked-lighting problem. Console vd0 == PC vd0 per group.
- Fix: `gfxworld_dynamics.conv_world_vertex_grouped(vd0, groups)`; assembler builds groups from PC
  vertexDataOffset0@12 + PC index max+1 per group and routes vd0 through it. Oracle vd0 58.56% ->
  **89.01%** (=32/36). vd1 (swap2, stride-4, alignment-independent) and indices unaffected.

Corrected geometry-region oracle: vd0 89.01% (32/36, tangent cosmetic) | vd1 94.18% | indices 97.30%
| surfaces 69.20% (PC-zero srfTriangles mins/maxs + material ptr). GfxWorld now diverges only 3.08%
from genuine (was 11.1%). Diagnostic artifact: `mp_raid_GEOMDIAG3_grouped.ff` (converted
vd0/vd1/indices via group-aware path + genuine surfaces) — READY for hardware load.

## (obsolete) Original Cemu protocol
Break at `0x029613e0`, filter `stride([r4+0x38])==36` (world), read `addr=[r4+0x24]`; set a
hardware WRITE watchpoint on that descriptor's `+0x24` word; the write fires in the BUILDER ->
capture PC + whether the count comes from a struct load or an index scan. See session handoff.
