# HANDOFF — Track C tail: XModel GX2 surface converter  🟡 CORE DONE, 3 pieces remain

Standalone doc. The XModel PC→console converter is now: **body + bone data byte-exact (prior), and
the XSurface + vertex/index buffers built & validated (this session).** Three bounded pieces remain
before an XModel is fully convertible for a no-backbone map: **materialHandles wiring, skinned
surfaces, and the post-surface tail.** Independent of Track E — validate against the matched-pair
oracle.

## ✅ DONE & VALIDATED (this session)
`native_linker/xmodel_convert.py`:
- `convert_surface_header` (80 B → 128 B)
- `_convert_vertlist` (XRigidVertList + collision trees/nodes/leaves)
- `convert_xmodel_surfaces` (full `surfs[ns]` header block + all per-surface dynamic data)
`native_linker/validate_xmodel_surface.py` — matched-pair oracle (joins by model name + surface idx).

**Header map PC80→CON128 (empirically pinned, NOT struct_layout):** head identical; pointer slots
relocate — `verts0 PC@32→CON@52`, `vertList PC@40→CON@96`, `partBits[5] PC@48→CON@108`; **new console
field `verts1@72`** (synthesized second stream, FOLLOW).

**Per-surface dynamic order (all linear — NO GX2 tiling):**
`verts0 (24·vc) → verts1 (8·vc) → vertList (+trees) → triIndices (6·tc)`.
> The old handoff's "sync GX2 tiling with the geometry session" note was a **red herring for model
> surfaces** — they're contiguous and `latte_vertex.pc_vertex_to_console` re-encodes them byte-exact
> with no tiling. (Tiling applies only to *world* vd0, not model surfaces.)

**Substructs:** vertList = 4×u16 + ptr; tree = 6 f32 + counts/ptrs; node = 8×u16; leaf = 1×u16.

**Validation:** headers 834/834 exact (masked omap ptrs) · dynamic 215/260 byte-exact-modulo-lossy ·
**self-consistency (resync) 260/260 (mp_raid) + 35/35 (zm_transit)**, incl. multi-surface ns=2–14.

**Two inherently non-reproducible regions (documented, NOT bugs):**
- verts0 normal/tangent — PC's 10-bit ThirdBased frame already lost the precision.
- Collision-tree node counts — the console linker rebuilds the surface BVH (nc 18 vs PC 20, leaves
  match). Converter copies PC's tree verbatim → self-consistent + loadable, just not byte-identical.
- Weapon `*_view` models diverge wholesale (Wii U re-authored those meshes — different vert/tri
  counts). Same viewmodel caveat the body converter flags.

## 🔧 REMAINING (ordered by criticality)

### 1. materialHandles wiring — DO FIRST (critical path)
Surfaces reference their material through `materialHandles`; without it a converted surface doesn't
know its material → wrong render or crash. Wire the `materialHandles[]` pointer relocation through the
omap (same reloc convention as `convert_material`/`conv_surface`). This is what makes the surface
converter *usable*, not just validated.

### 2. Skinned surfaces (flags&2) — REQUIRED (zombies path), not deferrable
Currently raises `NotImplementedError`. **Must be implemented** because **zombies maps introduce new
characters + wonder weapons, which are skinned, and ZM map zones are self-contained** (zm_transit
carries 1392 models inline vs mp_raid's ~2 — the skinned content lives IN the map zone, unlike MP
where players/weapons come from common_mp).
- Span already scoped in `xmodel_pc`: for `flags&2`, before verts0 there is
  `vertsBlend (Σ 1,3,5,7·vertCount[j], u16)` + `tensionData (Σ vertCount, f32)`.
- Convert: endian-swap the blend weights (u16) and tension (f32) alongside verts0.
- **Validate against the ZM map zone directly** (zm_transit) — NOT common_mp (ZM models are inline
  there; MP would have almost none). Mode-dependent oracle, same rule as the rest of XModel.
- **First: scan a zm map for `flags&2` count** to size the job and catch any special animated variant
  (high bone-influence characters, wonder weapons) before building — confirm plain vertsBlend/
  tensionData covers them.

### 3. Post-surface tail — lower priority (after 1 & 2)
Stream order after surfaces: `materialHandles → collSurfs → boneInfo → himip → physPreset`. collSurfs
matter for collision, physPreset is small; neither blocks a first *render*/load. Convert + relocate
after materialHandles + skinned are done.

## Oracle location — DEPENDS ON GAME MODE (verified)
- **MP model** → `common_mp` (models aliased out of map zones; join by name). common_mp.zone (console)
  vs PC ff/common_mp.zone (PC).
- **ZM model** → **the ZM map zone itself** (self-contained; zm_transit inline). NOT common_zm.
Confirm any asset type-id empirically (WiiU console type-ids are shifted; console type 6 = Material).

## Pinned facts / traps
- Console XSurface = **128 B** (PC 80). struct_layout says 64 — WRONG (wrong-variant, same as Material
  112-vs-104). `xmodel_probe.SURF=128` confirmed by resync across 470 models.
- Model vertex stride 24+8 — DISTINCT from world vd0's 36 B; no tiling for model surfaces.
- Full XModel stream order: body → bones → surfaces(+verts/index) → materialHandles → collSurfs →
  boneInfo → himip → physPreset.
- `himipInvSqRadii` + `memUsage` are console-computed body fields (already params on the body converter).

## Files / rules
`native_linker/xmodel_convert.py`, `native_linker/validate_xmodel_surface.py`,
`native_linker/xmodel_pc.py`, `wiiu_ref/latte_vertex.py`, `wiiu_ref/xmodel_probe.py`,
`native_linker/validate_xmodel.py`. Never write under `E:\`.

## Done-when (whole XModel complete)
A full XModel (body+bones+surfaces+materialHandles+skinned+tail) converts, validates vs the
mode-correct oracle (byte-exact except the lossy frame bytes + rebuilt-BVH counts), and resyncs onto
the next asset — for both a rigid MP model (common_mp) and a **skinned ZM model (zm_transit)**.
