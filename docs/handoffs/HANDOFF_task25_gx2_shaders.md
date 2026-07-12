> ✅ **COMPLETED (2026-07-03).** The SOLVE phase produced the byte-verified layout (see
> `WIIU_UNLINK_STATUS.md` §0g) and the IMPLEMENT phase landed it in OAT
> (`materialtechniqueset_console.{h,cpp}` + `T6::LoadConsoleMaterialPass`). Genuine `common_mp` now reads
> 49 assets. This document is retained for reference. The next blocker is task #26 (x64 reused-memory
> alias artifact).

# Handoff: solve the console (Wii U GX2) shader layout — task #25

**Task:** reverse-engineer the console (Wii U) `MaterialVertexShader` / `MaterialPixelShader` / shader-program
layout for Black Ops II (T6) fastfiles, and deliver a byte-accurate layout table. This is the SOLVE phase
only (pure Python triangulation, no C++/OAT build). The IMPLEMENT phase happens back in the main session.

Working directory: `C:\Users\Tony - Main Rig\Downloads\Testing enviroment`.

## Read first, in order
1. `WIIU_UNLINK_STATUS.md` §0g — the diagnosis and this task's brief. §0f — the *already-solved* console
   GfxImage layout (your template: same kind of problem, same method, same deliverable format).
2. `wiiu_ref/gfximage_probe.py` — the triangulation tool that solved GfxImage. Copy its approach
   (find console Material bodies by name-string-at-body-end, then walk the dynamic stream).
3. `SESSION_2026-07-02_ACCOMPLISHMENTS.md` — what's already solved (don't re-derive it).

## Context you must NOT re-derive (already established and verified)
- BO2 PC is 32-bit, so PC and console zones both use 4-byte pointers. Console divergences vs the PC struct
  are: dropped ID3D11 `void*` fields, array-count changes, `CONSOLE_MAX_ALIGN=4`, and — for GfxImage and
  (you're proving) shaders — a *different member set* that needs a hand-written console read path.
- **Console `MaterialTechniqueSet` = 136 bytes**: `name`(ptr) + `worldVertFormat`(u8)+pad + `techniques[32]`
  (NOT [36]).
- **Console `Material` = 104 bytes** (solved, §0f/§0c). You reach shaders via a material's `techniqueSet`.
- **These are CORRECT on console (verified by instrumentation, do not touch):**
  - `MaterialTechnique` header: `{ const char* name; uint16 flags; uint16 passCount; MaterialPass passArray[passCount]; }` — 8-byte header then `passCount` inline passes.
  - `MaterialPass` = **24 bytes**: `{ MaterialVertexDeclaration* vertexDecl; MaterialVertexShader* vertexShader; MaterialPixelShader* pixelShader; u8 perPrimArgCount; u8 perObjArgCount; u8 stableArgCount; u8 customSamplerFlags; u8 precompiledIndex; u8 materialType; MaterialShaderArgument* args; }`. In the failing techset these all read sane (all three shader ptrs FOLLOW, arg counts 1/1/3).
  - `MaterialVertexDeclaration` is already handled as a `?36:116` console conditional — verify it in passing but it's probably fine.

## The exact diagnosis (where it breaks)
Instrumenting the generated techset loader on genuine `common_mp`: the chain reads correctly down to the
shader program, then:
- vertex `GfxVertexShaderLoadDef.programSize` reads **0x0**
- pixel `GfxVertexShaderLoadDef.programSize` reads **0xffffffff** (a FOLLOW marker, not a size) →
  `Load<char>(program, 0xffffffff)` → 4 GB read → `XFILE_BLOCK_VIRTUAL overflowed`.

So the **console shader-program struct is NOT the PC one.** PC layout is:
```
MaterialVertexShader      { const char* name; MaterialVertexShaderProgram prog; }   // 16 B
MaterialVertexShaderProgram { void* vs /*ID3D11, DROPPED on console*/; GfxVertexShaderLoadDef loadDef; } // PC 12, console drops vs -> 8
GfxVertexShaderLoadDef    { char* program; unsigned int programSize; }              // 8 B
```
On console this is almost certainly a **GX2 vertex/pixel shader structure** (GX2VertexShader / GX2PixelShader:
a register block, program size, program pointer, shader mode, uniform-block/sampler/loop tables, etc.) —
the same situation as the inline GX2Texture inside GfxImage. Your job is to find its real byte layout.

## Method (copy gfximage_probe.py)
1. Find console `Material` bodies in `wiiu_ref/mp_raid_genuine.zone` (name ptr FOLLOW at +0, name chars at
   +104). Follow `techniqueSet` when it is FOLLOW (an inline `MaterialTechniqueSet`), or scan standalone
   `TECHNIQUE_SET` assets.
2. Walk `MaterialTechniqueSet(136)` → `techniques[32]` (follow the FOLLOW slots) → `MaterialTechnique`
   (8-byte header + `passCount`×`MaterialPass(24)`) → per pass, the `vertexShader`/`pixelShader` FOLLOW
   pointers → the shader body.
3. At each `MaterialVertexShader`/`MaterialPixelShader`, use the **name-string-at-body-end ruler** (like
   GfxImage): `MaterialVertexShader.name` — when FOLLOW, its chars land right after the shader body, so
   body-start → name-string distance = the console shader struct size. Confirm the modal size across many
   samples, then map fields. Shader names in T6 look like hashed tokens (e.g. `z33feqw…`) — printable,
   null-terminated. If `name` is an alias, use the next FOLLOW datum (the program bytes) as the ruler.
4. Locate `programSize` and the `program` bytes: the program is a big blob (GX2 microcode); its length
   should equal a size field you can find in the body. Verify by chaining: `body + name + program` must land
   exactly on the next pass's shader / next technique for many samples (the resync test that nailed GfxImage
   at 328).
5. Note the ZoneCode reorder if any (GfxImage loaded `name` first; check whether the shader loads name or
   program first by which one sits immediately after the body).

## Deliverable
A byte-table in the same form as `WIIU_UNLINK_STATUS.md` §0f, covering:
- console `MaterialVertexShader` (size, field offsets, which are little-endian GX2 words vs big-endian),
- console `MaterialPixelShader` (mirror),
- the shader-program sub-structure: where `programSize` lives, where the program bytes are, endianness,
- the **stream-consumption formula** per shader (`size + name chars if FOLLOW + program bytes + …`),
- how a `MaterialPass` references its shaders (FOLLOW inline vs alias),
- and a saved genuine sample (like `wiiu_ref/console_gfximage_sample.bin`) plus the probe script
  (`wiiu_ref/shader_probe.py`).
Write it into `WIIU_UNLINK_STATUS.md` §0g (replace the "SOLVE (fork)" bullet with the solved layout) and
note it in the `wiiu-native-unlinker` memory file.

## Verification / success criteria
- Your chaining/resync test passes on many mp_raid + zm_transit techsets (like GfxImage's 383 samples).
- Sanity: a real vertex/pixel shader `programSize` is a few hundred to a few thousand bytes of GX2 microcode
  (NOT 0x0 or 0xffffffff). The values that broke OAT were `programSize=0x0` (vertex) / `0xffffffff` (pixel).

## Don't chase
- `mp_raid` asset 2 (an anomalous empty `Glasses`, VIRTUAL 0x5221) is a separate known blocker — ignore it;
  use `common_mp` and later mp_raid techsets for shader samples.
- Don't touch `MaterialTechnique`/`MaterialPass`/`MaterialVertexDeclaration` — verified correct.
- No OAT/C++ build needed; this is Python triangulation only, so it won't collide with the main session
  (which owns the `tools/ref_oat/build` tree).

When you deliver the byte-table, the main session implements it as a hand-written console branch
(`Actions_MaterialTechniqueSet::LoadConsole…` + the `ZoneLoadTemplate` `PrintLoadMethod` hook), mirroring the
GfxImage implementation in `gfximage_actions.cpp`.
