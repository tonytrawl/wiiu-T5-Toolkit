# HANDOFF — GfxWorld geometry pipeline SOLVED + hardware-confirmed (2026-07-06)

Standalone status for the main session. The GfxWorld world-geometry render blocker (the "last
render wall" from `HANDOFF_geometry_vd0.md`) is **CLOSED and hardware-validated on Cemu**. This doc
is the single source of truth for what happened, what's proven, what changed in code, and what's
left. Supersedes the "unknown offset / reorder / baked-lighting" framing everywhere.

---

## 0. Bottom line
A PC map's world geometry, converted through the native pipeline, **renders correctly on Wii U**.
Confirmed by loading `mp_raid_GEOMDIAG3_grouped.ff` in Cemu: geometry unwarped, lighting sane and
playable (only faint specular/lightmap cosmetics off). The whole effort turned out to hinge on ONE
real bug (vd0 group padding); the scary parts of the old handoff (unknowable offset, console
reorder, baked-lighting re-encode) were **misreads**, now disproven.

## 1. What was actually true (replaces the old handoff's assumptions)
- **Per-surface vertex offset = `vertexDataOffset0` (srfTriangles @12)** — a STORED byte offset into
  vd0. Loader ptr = vd0_base + vertexDataOffset0. NOT a loader accumulation, NOT unknowable. (Old
  handoff said this field was "ruled out" — that was wrong.)
- **Indices are 0-relative per vertex GROUP; `baseIndex`@44 is cumulative** (Σ triCount*3), 100%
  across 5281 surfaces. Surfaces sharing a vertexDataOffset0 share a vertex group.
- **NO console reorder.** PC vd0 == genuine console vd0, 100% of positions (162752/162752), 394/394
  groups, when read group-aware. Full vertex is 32/36 byte-exact (only 4 tangent bytes differ =
  cosmetic packed repack).
- **NO baked-lighting re-encode.** The earlier "color/normal 85% differ" was a flat-read artifact.
- **THE ONE REAL BUG:** vd0 is not a flat 36B array. Each group = `vertexCount*36` bytes then
  **padded to a 16-byte boundary**. A flat 36-stride conversion drifts out of alignment after the
  first padded group and corrupts all later groups → warped geometry. Fix = convert GROUP-AWARE.
- **vd1** = secondary stream, stride 4 (2× u16, likely f16 lightmap UVs), converted by **swap2**
  (alignment-independent). Surfaces store `vertexDataOffset1`@28. Trivial, not deep RE.
- **srfTriangles mins/maxs are ZERO on PC** (0/5281 nonzero); console bakes real bounds there. Left
  zero for now (GfxSurface.bounds@56 IS populated and matches). Prime suspect if culling ever
  misbehaves — bake from verts then.

## 2. Code changes landed (native_linker/)
- `gfxworld_dynamics.py`:
  - `conv_world_vertex_grouped(vd0, groups)` — group-aware vd0 conversion (THE fix).
  - `conv_surface(pc, stride=80, reloc=None)` — GfxSurface field-aware swap; `material@48` via the
    `reloc(pc_ptr)->console_ptr` convention (sentinels preserved), matching material/xmodel/fx
    converters. Identity default = oracle only; real map MUST pass omap-backed reloc.
  - REGION_SPEC: `draw.indices`→swap2, `draw.vd.data`→world_vertex (vd0) / swap2 (vd1, 2nd span).
- `gfxworld_assemble.py`: per-key FIFO span pairing (handles vd0/vd1 dup key + console-only gen
  regions); builds vd0 group list from PC vertexDataOffset0 + per-group index max; routes vd0 to
  `conv_world_vertex_grouped`; `skip_convert=` param for diagnostic isolation; per-region oracle
  match-rate reporting; explicit UNCONVERTED tagging.

## 3. Oracle state (mp_raid, coverage 48%; all residuals explained, no wiring bugs)
| region | method | oracle match | residual |
|---|---|---|---|
| draw.vd0 | conv_world_vertex_grouped | 89.01% | =32/36, tangent bytes cosmetic |
| draw.vd1 | swap2 | 94.18% | minor (lightmap) |
| draw.indices | swap2 | 97.30% | minor |
| dpvs.surfaces | conv_surface | 69.20% | PC-zero mins/maxs + material ptr (expected) |
All deterministic regions (swap4/swap2/fields/entry4) = 100%.

## 4. Artifacts
- ✅ `mp_raid_GEOMDIAG3_grouped.ff` — HARDWARE-CONFIRMED. Genuine mp_raid + PC-converted
  vd0/vd1/indices (group-aware) + genuine surfaces. Loads & renders correct on Cemu. Zero RSA sig
  (relies on confirmed RPL sig-patch). Intentional-divergence DIAGNOSTIC, not a byte-genuine repack.
- 🗑️ `mp_raid_GEOMDIAG1.ff`, `mp_raid_GEOMDIAG2_fullPC.ff` — carry the OLD flat-conv bug; delete.
- `mp_skate.ff` (copied from E:\...\pluto_t6_dlcs\zone\all) + `mp_skate_pc.zone` (163MB, decrypted
  via tools/ff_decrypt.py) — the real next target (PC-only retail DLC, no console backbone).
- `wiiu_ref/_running.rpl` = the RPL Cemu actually runs (installed .orig; runtime addr = file+0x2000).

## 5. Key tooling facts (for whoever continues)
- PC .ff → zone: `tools/ff_decrypt.py` (`detect_platform` + `decrypt_ff`). Zone → WiiU .ff:
  `tools/ff_pack.py::pack_ff(zone, name, endian='>')` (zero sig).
- OAT `Unlinker.exe` (tools/ref_oat/build/bin/Release_x64/) parses mp_skate cleanly (0 errors);
  `--list` and `--include-assets gfxworld`. Debug prints per-asset `STREAM_pos` — but that's a
  DIFFERENT zone memory-block than our flat body offsets (block-address mapping TODO).
- Native PC walker (`pc_walk.py`) drifts at asset 632 (XMODEL) — can't reach GfxWorld (asset 800)
  on mp_skate. This is why OAT front-end is needed.
- Disassembly of the running RPL: capstone installed; `wiiu_ref/rpl_sigpatch.py` `_sections`/
  `_sec_bytes`; text = section idx 1, vaddr 0x02000000.

## 6. Remaining work for a real mp_skate build (render side DONE; this is INPUT plumbing)
1. **OAT front-end (gate for everything).** Decide: does OAT emit a usable raw GfxWorld blob, or
   must we build the STREAM/VIRTUAL-block → flat-offset map to consume OAT's `STREAM_pos`? Adopt OAT
   for PC unlinking (it's complete/correct; native walker isn't) — keep native for console-side.
2. **No-backbone assemble.** mp_skate has no genuine console GfxWorld baseline, so the console-only
   regions currently `reuse`/`gen`/`console_gx2` (reflection probes, lightmaps, cells,
   materialMemory, GX2 textures, occluders, streamInfo) must be GENERATED, not reused. This is the
   real remaining chunk.
3. **Converted surfaces + real material omap reloc** (conv_surface is reloc-ready; needs the live
   omap). Then the cheap build-#2 test: converted surfaces (PC-zero bounds) — does culling misbehave?
   If yes, bake srfTriangles mins/maxs from verts.
4. Then build mp_skate .ff → Cemu.

## 7. Do-not-repeat traps
- vd0 is GROUP-PADDED (16B). Never convert it flat. (This burned a whole hardware cycle.)
- Don't trust flat byte-diffs of vd0 as "reorder"/"baked lighting" — read group-aware.
- Cemu runs the INSTALLED rpl (mlc01\...\.orig), runtime = file+0x2000; the loose
  `wiiu_ref/t6mp_cafef_rpl.rpl` is a DIFFERENT build.
- Genuine-surface + PC-vd0 mixing is NOT a clean test (baseIndex differs on 119 surfaces); use
  fully-consistent sets or genuine-equivalent converted vd0.
- Don't edit files under E:\ (installed game); copy out first.
