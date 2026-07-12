# HANDOFF — Geometry build #2: converted-surfaces culling check

Standalone start doc. Small, well-scoped hardware validation. Goal: confirm the **surface converter**
(`conv_surface`) renders correctly on hardware when its PC-zero `srfTriangles` bounds are used, i.e.
check whether zeroed mins/maxs cause DPVS to cull surfaces wrong. This de-risks the surface converter
before the no-backbone build depends on it. The geometry render pipeline is already
SOLVED/hardware-confirmed — this isolates the one remaining surface variable.

## Background — why this specific test
- **Build #1** (`mp_raid_GEOMDIAG3_grouped.ff`, already hardware-confirmed) used **converted
  vd0/vd1/indices + GENUINE surfaces**. It rendered correct: geometry unwarped, lighting sane. That
  proved the *vertex/index* conversion but deliberately kept genuine surfaces to avoid a confound.
- The surface converter (`conv_surface`) is byte-analyzed and understood (oracle 69.20% = exactly the
  two known, non-bug diffs): (1) PC stores **all-zero `srfTriangles` mins/maxs** (verified 0/5281
  nonzero) — the console **bakes real bounding boxes** there; (2) the material pointer @48. Every
  geometry scalar (`vertexDataOffset0/1`, firstVertex, vertexCount, triCount, baseIndex, bounds@56)
  converts byte-exact.
- **The open question this build answers:** those zero mins/maxs feed **DPVS culling**. Degenerate/zero
  boxes may make surfaces cull incorrectly — the prime suspect for the historical "geometry invisible
  unless I move around" warping. Build #1 couldn't catch this (it used genuine baked bounds).

## The build
Assemble an mp_raid `.ff` with the geometry regions PC-converted **including converted surfaces**:
- `draw.vd.data` → `conv_world_vertex_grouped` (group-aware; NOT flat — the 16-B group padding bug)
- `draw.vd1` → `swap2`
- `draw.indices` → `swap2`
- `dpvs.surfaces` → `conv_surface` (material@48 relocated via omap; mins/maxs left PC-zero)
- everything else reused from the genuine baseline (Raid diagnostic)
Then `wiiu_ff.py pack` → **sig-patch for Cemu** → load.

Name it clearly as an intentional-divergence diagnostic (e.g. `mp_raid_GEOMDIAG4_convsurf.ff`) so
nobody mistakes it for a byte-genuine repack.

## Expected outcomes / decision
- **Geometry renders intact and un-warped** → the surface converter is validated on hardware, zero
  bounds are fine (the engine recomputes or doesn't rely on them for these surfaces). Surface converter
  is cleared for the no-backbone build. Lighting will still be flat/bright on the baked vd0 color/normal
  layers — that's the known unbaked-vd0 cosmetic cost, not a defect.
- **Geometry pops in/out or is invisible until you move / culls wrong** → the zero mins/maxs ARE used
  for culling. Fix: **bake real per-surface bounding boxes from the vertex data** (compute mins/maxs
  over each surface's converted vertices) in `conv_surface`, rebuild, re-test. This is the concrete
  next step if the check fails.

## Files / traps
- `native_linker/gfxworld_assemble.py` (assemble path, region splice), `native_linker/gfxworld_dynamics.py`
  (`conv_surface`, `conv_world_vertex_grouped`), `WiiU_FF_Studio/wiiu_ff.py` (pack), sig-patch tool.
- **Traps (from the solved geometry work):** vd0 is 16-B GROUP-padded — never convert flat; there is no
  reorder and no baked-lighting re-encode (both were flat-read artifacts); Cemu runs the **installed**
  rpl (runtime = file + 0x2000; `wiiu_ref/_running.rpl` is the live one); don't edit under `E:\`.
- Full geometry context: `HANDOFF_geometry_vd0.md` (section 0-SOLVED) + `FINDINGS_offline_RE_vd0_offset.md`.

## Why it's worth doing now
It's the last unknown on the surface converter, it's a single build + load, and doing it on raid (fully
buildable today) means when the no-backbone map (mp_skate) build happens, converted surfaces are already
hardware-proven — so if that build shows culling problems you'll know it's map-specific input, not the
converter.
