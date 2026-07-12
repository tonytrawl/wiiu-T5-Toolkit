# FINDINGS — Lighting repack (POLISH session, 2026-07-10)

**The "renders darker" defect is root-caused to two mis-converted GfxWorld vertex-stream
field classes, both now solved with 2-map byte-exact re-encodes.**
Module: `native_linker/lighting_repack.py` (new; owned files untouched).
Validator: `native_linker/lighting_repack_validate.py`. Probes: `lighting_repack_probe*.py`.

## 1. vd0 tangent (@32..36 of the 36B world vertex) — the main defect

The old `conv_world_vertex` swap2 was byte-correct for only **0.73%** of tangents (1,187 of
161,710 raid verts). Every other field (pos/w/color/normal/uv) is 100% exact under the old
conversion — the tangent was the ONLY wrong vd0 field. A wrong tangent dword corrupts the
tangent frame of every normal-mapped world surface → wrong specular/normal-map response =
the registered lighting-level defect.

**The rule** (console re-packs the PC 10:10:10 tangent shifted one bit, carrying ACROSS the
two u16 lanes): with `lo, hi` = the two LE u16s of the PC tangent dword,

```
console_u16[0] (BE) = (lo >> 1) | (hi15 << 15)
console_u16[1] (BE) = (hi << 1) | lo0
```

Validation: **mp_raid 162,752/162,752 verts byte-exact (100.0000%); mp_dockside 120,800
verts — 120,790 exact + 10 divergent in the UV field only** (see §3; not tangent-related).

## 2. vd1 is NOT a flat swap2 stream — per-group elements with a vertex-color word

vd1 = per-surface-group elements of stride 4/8/12/16 (from `vertexDataOffset1@28`; group
element count = max group index + 1, extent = next group offset). Element = 1..3 **f16
lightmap-UV layer words** (convert swap2) + optionally trailing **RGBA8 vertex-color
word(s)** (convert VERBATIM — bytes, no endianness). Observed layouts (both maps):
s4=[UV]; s8=[UV,UV] or [UV,color]; s12=[UV,UV,UV] or [UV,UV,color]; s16=[UV,UV,color,color].
The old flat swap2 byte-reversed every color word (wrong vertex tint on blended/terrain
surfaces).

**Column classification (PC-only, no oracle needed):** column 0 is always UV; each later
column is majority-voted: a word is "UV-plausible" iff each u16 half is ±0 or a normal f16
with exponent field in **[5, 17]** (|x| ∈ [2^-10, 8)); a column with ≤50% plausible words is
color. Groups whose extent is not an integral 4/8/12/16 stride (a handful of offset-sharing
subranges per map) fall back to the same vote per uncovered WORD.

Validation: **byte-exact 371,876/371,876 (mp_raid) and 96,148/96,148 (mp_dockside) — 0 diff
bytes on both maps.** (Ground-truth column classes were derived from the genuine consoles
first; the PC-only vote reproduces them 100% on both maps: 111/111 + all dockside groups.)

## 3. Registered divergence class (cosmetically nil)

10 of 4.4M dockside vd0 verts differ ONLY in the UV field, values being f32 SUBNORMALS
(~1e-39) on degenerate vertices; the console linker flushed/altered denormal low bits (e.g.
PC `0x000ca5d0` vs console `0x000ca5cf`). Not reproducible from PC data at the bit level,
invisible at render. Raid has zero. (Same class as CAVEATS' lossy registrations.)

## 4. Caveats / limits

* The [5,17] exponent window is calibrated on raid+dockside (gray RGBA colors alias to
  large-|x| f16s → rejected; smallest genuine layer-UVs have exp 6 → admitted). A future map
  could in principle defeat the vote (e.g. a color column whose bytes all alias into the
  window). `conv_vd1` takes `col_override={(group_off, col): is_color}` for manual pinning;
  a mis-vote's visual symptom is a wrongly tinted surface, not a crash.
* Console GfxWorld walker (gfxworld_probe2) drifts on the DLC map (dockside) — region-order
  variance; NOT needed for conversion (PC-side walk is what the converter uses). Dockside
  genuine vd0 was anchored by searching for the converted first PC vertex (@0x2d9fe51 in
  mp_dockside_wiiu.zone).

## 5. Integration note (assemble session — few lines, owned files)

1. In `gfxworld_dynamics.conv_world_vertex` (or via `conv_world_vertex_grouped`'s inner
   call): replace the `(32, 34)` swap2 pair with `lighting_repack.conv_tangent(v[32:36])`
   — or call `lighting_repack.conv_world_vertex36` instead of `conv_world_vertex`.
2. In `gfxworld_assemble.assemble`: where the 2nd `draw.vd.data` span is currently forced to
   `swap2`, route it to `lighting_repack.conv_vd1(pc_vd1_bytes, groups)` with
   `groups = lighting_repack.vd1_groups(PC, surf_span_start, nsurf, idxarr, nidx, vd1_size)`
   (same surface/index spans already used to build `vd0_groups`).
3. Re-run `lighting_repack_validate.py` after wiring: both maps must print 0 diff bytes for
   vd1 and 100% vd0 (mod the 10-subnormal dockside class).

A Cemu A/B artifact was NOT built this session; after integration, any raid build via the
existing oracle pipeline will now emit genuine-identical vd0/vd1, so a dedicated GEOMDIAG
lighting build is equivalent to the existing byte-exact proof.
