> ✅ **SOLVED & HARDWARE-CONFIRMED (2026-07-06).** This blocker is closed. There was NO real
> "per-surface offset unknown," NO console reorder, and NO baked-lighting re-encode — those were
> misreads. The offset is the stored `vertexDataOffset0` (byte offset into vd0); indices are
> 0-relative per group; baseIndex is cumulative. The ONLY real bug was that vd0 is laid out
> per-group as `vertexCount*36` bytes **padded to 16 bytes**, so vertex conversion must run
> GROUP-AWARE (a flat 36-stride pass drifts and warps). Fix: `conv_world_vertex_grouped` +
> assembler group build. `mp_raid_GEOMDIAG3_grouped.ff` (PC-converted vd0/vd1/indices) loads and
> renders correctly on Cemu: geometry unwarped, lighting sane/playable (faint tangent/vd1 cosmetic
> only). Full story in `FINDINGS_offline_RE_vd0_offset.md` ("MAJOR CORRECTION"). Remaining is
> mp_skate INPUT plumbing (OAT front-end + no-backbone generators), not render.

# HANDOFF — GfxWorld geometry blocker (new-map vd0 per-surface offset + vertex count)

Standalone start doc for a fresh session. Goal: make a **new** PC map's world geometry render
on Wii U. Everything else in the GfxWorld pipeline is solved and hardware-confirmed; this is the
last render wall. Read this top-to-bottom before touching code — the trap here is re-deriving
things three prior sessions already nailed down.

---

> ⚠️ **Everything in sections 0–2 below was the ORIGINAL (WRONG) theory. It is preserved only as a
> record of what was disproven — do NOT act on it. The real, hardware-confirmed solution is in
> section 0-SOLVED immediately below and in `FINDINGS_offline_RE_vd0_offset.md`.**

## 0-SOLVED. What was actually true (hardware-confirmed 2026-07-06)
- **The per-surface offset IS a stored field: `vertexDataOffset0` (@12)** — a plain byte offset into
  vd0. `ptr = vd0_base + vertexDataOffset0`. It was never loader-computed. (The old "ruled out
  against 167 GPU draws" claim was a flat-read artifact.)
- **There is NO console reorder.** PC vd0 == genuine console vd0 for 100% of positions (394/394
  groups); full vertex 32/36 byte-exact (tangent cosmetic). Convert in PC order, verbatim.
- **There is NO baked-lighting re-encode** in color/normal — also a flat-read artifact.
- **The ONE real bug:** vd0 is laid out per group as `vertexCount*36` bytes **padded to 16 bytes**.
  A flat 36-stride conversion drifts after group 0 and warps everything. Fix = **group-aware**
  conversion: `native_linker/gfxworld_dynamics.py::conv_world_vertex_grouped` + the assembler's vd0
  group-list build.
- **vd1** = stride-4 (2× u16, likely lightmap UVs) → `swap2`. Surfaces reference it via
  `vertexDataOffset1 @28` (converted by `conv_surface`).
- **indices** = `swap2`, 0-relative per group, `baseIndex` cumulative.
- **surfaces**: `srfTriangles_t` mins/maxs are zero on PC (console bakes them) — left zero; only a
  suspect if culling misbehaves. `conv_surface` relocates material@48 via the omap.
- **Proof:** `mp_raid_GEOMDIAG3_grouped.ff` (PC-converted vd0/vd1/indices) loads & renders correct on
  Cemu — geometry unwarped, lighting sane/playable. Oracle: vd0 89% (=32/36) · vd1 94% · indices
  97% · surfaces 69% (PC-zero bounds + matptr) · all deterministic regions 100%.

Remaining is NOT render — it's mp_skate INPUT plumbing: the OAT front-end to locate/read a
no-backbone map's GfxWorld (native walker drifts @asset 632), the no-backbone generators for
console-only regions (probes/lightmaps/cells/materialMemory/GX2), converted-surfaces + live omap,
and a cheap zero-bounds/culling check. See the main native-converter handoff + FINDINGS doc.

---
<details><summary>ARCHIVED — original disproven theory (sections 0–2, do not act on)</summary>

## 0. The one-sentence problem  [DISPROVEN]
The console loader places each world surface's vertices at a **loader-computed byte offset** into
the shared vertex-data buffer (vd0). That offset is **not stored in any serialized surface field**,
and the console **reorders** the world vertices (GX2 vertex-cache optimization). So when we convert
a PC map we don't know (a) where each surface's verts start in vd0, nor (b) how many verts each
surface owns. Without that, our vd0 blob is self-inconsistent and geometry renders warped.
[WRONG: offset = vertexDataOffset0; no reorder; the real bug was 16B group padding.]

## 1. What was thought PROVEN  [PARTLY WRONG — see corrections]
- World vertex **stride = 36 bytes** [TRUE], per-group padded to 16B [the missed detail].
- Per surface: attrib-ptr = vertex block start, baseVertex=0, indices 0-relative [TRUE].
- "Ruled OUT vertexDataOffset0 as the offset against 167 GPU draws" [FALSE — it IS the offset].
- "vertexCount@40 is 0 for ~99%, not the count" — irrelevant; vd0 is group-padded, no per-surface
  count lookup was ever needed.

## 2. The unknown lives in the LOADER  [FALSE — it was a stored field]
The whole "reverse the loader via a GX2SetAttribBuffer breakpoint" thread (Thread A/B, the
R_LoadWorld/Load_GfxWorld addresses, the 55-surface GPU capture) turned out UNNECESSARY. The offset
was `vertexDataOffset0` all along. Preserved here only so nobody re-opens it.
</details>

## 3. Files you will touch / read
- `native_linker/gfxworld_dynamics.py` — `REGION_SPEC`, `conv_world_vertex` (per-vertex convert DONE).
- `native_linker/gfxworld_assemble.py` — region walk + dispatch; where the generator plugs in.
- `wiiu_ref/gfxworld_probe2.py` — CFG with both-platform GfxWorld landmark offsets (body=1076
  console / 1028 PC; GfxWorld @ console 0x2b7029d, PC 0x3f34930).
- `wiiu_ref/crash_watchlist.md`, `wiiu_ref/rpl_symbolize.py` — loader addresses / symbolication.
- `DPVS_WALK_FINDINGS.md`, `wiiu_ref/dpvs_walk_full.py` — DPVS/surface walk reference.
- Reference OAT struct source (ground truth for srfTriangles/GfxSurface fields):
  `tools/ref_oat/build/src/ZoneCode/Game/T6/XAssets/gfxworld/gfxworld_t6_write_db.cpp`.

## 4. Validation ladder (each step gated on the previous)
1. **Unit:** recovered offset rule reproduces the 55 captured GPU offsets exactly. (No hardware.)
2. **Assemble:** generator produces a vd0 whose per-surface 0-relative indices never exceed that
   surface's block size; total vd0 size sane vs genuine.
3. **HW smoke (Raid null-test):** run the generator over Raid instead of reusing the genuine
   baseline; the map must still render correct. This proves the generator, not just the transplant.
   Build via the existing assemble path → `wiiu_ff.py pack` → Cemu.
4. **HW new-map:** run it on a real converted PC map (dust2) and confirm world geometry is
   un-warped.

## 5. Traps / do-not-repeat  (CORRECTED post-solution)
- **`vertexDataOffset0` @12 IS the per-surface offset.** (The earlier "falsified against 167 GPU
  draws" note was a flat-read artifact — ignore it.) `vertexDataOffset1` @28 is vd1's offset.
- **vd0 is 16-byte GROUP-padded — never convert it flat.** Use `conv_world_vertex_grouped`; a flat
  36-stride pass warps everything after group 0. This was the ONE real bug.
- Do NOT read flat byte-diffs as "reorder" or "baked lighting" — both were misreads of the group
  padding. There is no reorder; convert in PC order verbatim.
- Cemu runs the INSTALLED rpl (runtime = file + 0x2000); `wiiu_ref/_running.rpl` is the live one.
- Mixing genuine surfaces with PC-converted vd0 is NOT a clean isolation test — they must match.
- Do NOT edit files under `E:\...` (installed game) — copy out first; reading is fine.
- struct_layout's console GfxWorld is 1016B and WRONG for `draw` onward — use gfxworld_probe2
  landmarks (1076B), never struct_layout, for anything past the head.
- The genuine `gfxworld_raid_remapped.blob` transplant is a **null-test, not a converter** — don't
  mistake its green/lit boots for the geometry being solved.

## 6. Definition of done
A PC map converted through the native pipeline renders its world geometry correctly on Wii U
hardware (Cemu), with vd0 generated from PC source (no genuine-blob reuse for vd0/indices).
