# HANDOFF — XModel skinned surface: Latte skin-stream synthesis (or prove it's unneeded)

Standalone doc. Goal: make **skinned** XModel surfaces (flags&2) convert for the zombies path (ZM
characters + wonder weapons, which live inline in the ZM map zone). This is the last XModel gap.

## Honest state — this was NOT solved before (premise correction)
The native XModel session and **OAT independently hit the same wall** and documented it identically:
- `vertsBlend` IS writable — PC formula `(v0 + 3·v1 + 5·v2 + 7·v3) × u16`, byte-swap-identical.
- The **three console-only Latte skin streams CANNOT be derived from PC data** and are emitted absent
  by OAT (`tools/ref_oat/.../ConsoleWriterT6.cpp::WriteConsoleXSurfaceArray`, and
  `wiiu_ref/linker_findings.md` "Limitations").
- What *was* solved under a "skin" name is a DIFFERENT asset — the **GfxWorld siege-skin GPU shaders**
  (`gpuskin1..4bone.glsl`), transplanted verbatim (`ConsoleSiegeSkinTail.h`). That's a world-asset
  blob reuse, NOT the per-surface skin-stream. Don't conflate them (but it's useful — see step 2).

## Exact console layout (from OAT — use these offsets)
Console XSurface = 128 B. Relevant skin fields:
- `+16..+24` : `vertCount[4]` (4× u16) — per-influence-group vertex counts (v0..v3); size vertsBlend
  and the skin streams.
- `+24` : `vertsBlend` FOLLOW (writable).
- **`+28` and `+40` : the two skin-stream COUNTS** (OAT emits 0).
- **`+32`, `+36`, `+44` : the three skin-stream FOLLOW MARKERS** (OAT emits null).
- `+52` verts0, `+72` verts1, `+96` vertList, `+108..+128` partBits[5].
Native session's measurement: PC `tensionData` 8492 B → console skin streams **16836 B**, sized by the
`+28/+40` scalars. (OAT's `+28/+40` == native's `s28/s40` — same fields.)

## STEP 1 (do FIRST — may eliminate the whole task): prove whether the loader even needs them
OAT already built the experiment and never ran it to conclusion: `OAT_NO_SKIN` emits every skinned
surface **rigid** (no vertsBlend, skin streams absent, markers null / counts 0).
- Build a zone containing a skinned model with the skin streams **absent** (native: emit the surface
  rigid; OAT: `OAT_NO_SKIN=1`) and **Cemu-load it.**
- **If `XModel_Load` does not fault and the model renders** (it'll be frozen in bind pose — ugly but
  loadable) → **skinned ships rigid, no synthesis needed.** That's the biggest possible shortcut and
  it's one build+load away. For a first zombies *boot*, a bind-pose character is acceptable.
- If it faults → the streams are load-required; go to Step 2.
Record the result in memory either way — this question has been open in two efforts and never closed.

## STEP 2 (only if Step 1 faults): RE the skin-stream format
The format is **specified by the `gpuskinNbone.glsl` vertex declarations**, which are already
extracted in `ConsoleSiegeSkinTail.h` — their input attributes tell you exactly what the 3 streams
feed: `vsin_bone0/1/2/3`, `vsin_weight1/2/3` (+ pos/normal/tangent). So the streams are per-vertex
bone-index + weight data in a Latte hardware layout, one stream per additional bone influence (2/3/4
bone → 1/2/3 extra streams — matches "three streams").

Method (matched-pair oracle, same discipline as vd0/vd1):
1. Take a genuine console skinned model — **`viewmodel_hands_cloth`** (the pair the native session
   already aligned) or any `flags&2` model in `zm_transit` (console).
2. Extract its 3 skin streams at `+32/+36/+44` (sizes from `+28/+40`).
3. Diff against the PC model's `vertsBlend` + bone-index/weight data. Determine:
   - Is it a **deterministic re-layout** of data PC already has (bone indices + weights → Latte
     stream order)? → synthesizable, mirror it (like vd0's group-aware transform).
   - Or does it need data PC lacks? → then it's console-linker-computed; may need real generation or a
     defensible bind-pose stub (fall back to Step 1's rigid emit for that model).
4. Match the `gpuskinNbone` attribute layout so the stream feeds the shader correctly.

## Scope / priority
- **Not on the mp_skate (MP) critical path** — MP maps alias skinned content to `common_mp`, so an MP
  map zone has ~zero flags&2 models. Confirm with a `flags&2` scan of mp_skate.
- **Required for the ZOMBIES path** (zm characters/wonder weapons inline in the map zone). Schedule it
  with the zombies phase, after the first MP boot.
- The GfxWorld siege-skin SHADERS themselves (gpuskinNbone) are a **reuse-genuine blob** for any map
  (platform shaders, same everywhere) — `ConsoleSiegeSkinTail.h` + `WriteConsoleSiegeSkinShaders`
  already handle them; not a blocker.

## Files
- `tools/ref_oat/src/ZoneWriting/Game/T6/ConsoleWriterT6.cpp` (`WriteConsoleXSurfaceArray` — the
  OAT_NO_SKIN diagnostic + the exact field layout; `WriteConsoleSiegeSkinShaders`),
  `tools/ref_oat/.../ConsoleSiegeSkinTail.h` (the gpuskinNbone shader decls = the stream spec).
- `wiiu_ref/linker_findings.md` (skinned-surface limitations, siege-skin tail).
- `native_linker/xmodel_convert.py` (the `NotImplementedError` to replace), `wiiu_ref/xmodel_probe.py`,
  `wiiu_ref/latte_vertex.py`, `native_linker/validate_xmodel_surface.py`.
- Oracle: `viewmodel_hands_cloth` (console + PC), or `zm_transit` skinned models. Never write under E:.

## Bottom line
The scary part (synthesis) may not be needed at all — **run Step 1 first.** Two prior efforts proved
the streams aren't PC-derivable but neither tested whether the loader *requires* them. If bind-pose
rigid loads, zombies characters ship (static) with zero synthesis, and Step 2 becomes an
animation-quality polish rather than a boot blocker.
