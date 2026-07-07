# Side task findings — Are 360 / PS3 fastfile shaders related to Wii U GX2?

**Date:** 2026-07-05  **Scope:** read-only scouting report. No pipeline changes, no binaries.
**Verdict up front:** 360 → Wii U is **plausible but needs a microcode transpiler/recompile (not
byte-portable)**. PS3 → Wii U is **not viable** (different GPU vendor). 360 can therefore serve as a
shader source for DLC maps that have no genuine Wii U version, at meaningful engineering cost.

---

## What was actually inspected (evidence, not assertion)

| Platform | Source | How obtained |
|---|---|---|
| Wii U (Latte) | `wiiu_ref/mp_raid_genuine.zone` + `console_shader_sample.bin` | inline GX2 shader structs, already RE'd by this project (`shader_probe.py`) |
| Xbox 360 (Xenos) | `xbox ff/zm_transit.ff` → decompressed to zone via existing Unlinker (`OAT_DUMP_ZONE`, read-only) | located shader name strings, dumped adjacent microcode |
| PS3 (RSX) | `ps3 ff/zm_nuked.ff` | **could not decompress** — Unlinker's inflate fails on PS3 stream (`invalid block type`). Verdict from GPU architecture, which is definitive here. |

All work done in the session scratch dir on copies. No source `.ff`/zone was modified; Unlinker was
used read-only (`--list`); `tools/ref_oat` source was not touched.

---

## 1. Container / asset graph

All three consoles use the **same T6 fastfile asset graph** (MaterialTechniqueSet → MaterialTechnique
→ MaterialPass → {MaterialVertexShader, MaterialPixelShader}). The 360 zone is **big-endian** (PPC),
same as Wii U, and uses the same `0xFFFFFFFF` FOLLOW / aliased-pointer stream convention — I could
walk technique names (`pimp_technique_zprepass_…`, `pimp_technique_buildshadowmap_…`) and shader
names (`pimp_shader_transformonly_d4f4e04b.hlsl*packed`) in exactly the T6 layout this project already
documented for Wii U.

Key structural difference in *where* the microcode lives:
- **Wii U:** GX2 vertex/pixel shader struct is **inline** in the material (308 B VS regs / 232 B PS
  regs, big-endian), microcode is the first dynamic datum after the struct. (Documented in
  `wiiu_ref/shader_probe.py`.)
- **360:** vertex/pixel shader load-defs reference the Xenos microcode; the microcode blob sits in
  the same material region of the stream (e.g. the `transformonly` VS microcode was at zone
  `0x23988–0x23a50`, right after its name string).

## 2. Microcode family — the crux

### Wii U (Latte) — AMD R700 / TeraScale, GX2
GX2 program body is clause-based AMD R700 microcode (CF + ALU + TEX clauses; 64-bit CF words, ALU
words with embedded literals — e.g. the `…ecdf ea0d…` ALU patterns seen in the extracted blob).
Program sizes range ~0x190–0xb30 bytes across the zone. This is the **TeraScale VLIW5** ISA.

### Xbox 360 (Xenos) — ATI unified-shader, direct ancestor of R600
Extracted `transformonly` VS microcode (50 big-endian words). It is unmistakably **Xenos ISA**:
```
00100960 03500912 00120000 …        <- control-flow / exec clause setup
… 00c80700 0100c01b c08b0014         <- vfetch clause (0xC8 = vertex-fetch opcode)
14c80800 01006c6c 00a680ff
00c80100 0000a7a7 00af0104           <- repeated vfetch instructions, one per attribute
00c80200 0000a7a7 00af0105
… 00c80f80 3e000000 00e20101 004e4a00 00a29964   <- ALU/export + trailing CRC
```
The repeating `00c8 0X 00 … a7a7 00af 0X0X` are Xenos vertex-fetch instructions; the header words are
Xenos control-flow. This is AMD/ATI **clause-based unified-shader** microcode — the *same
architectural family* as R700 (CF + fetch + ALU clause model, VLIW), but a **distinct instruction
encoding** (Xenos predates and differs from TeraScale/R600).

### PS3 (RSX) — NVIDIA G70
Could not decompress with the current Unlinker, but the determination is architectural and not in
doubt: RSX is an NVIDIA G70/Curie part. Its vertex/fragment programs use NVIDIA's microcode
(NV_vertex_program / NV fragment-program style), which shares **no lineage** with AMD clause-based
ISAs. There is nothing to convert toward GX2 short of full recompilation from source.

## 3. Matched-material anchors (why a converter is testable)

Shader names embed a **hash of the source shader**, so an identical hash across platforms means the
*same source shader* compiled to two different targets:
- `pimp_shader_transformonly_**d4f4e04b**` appears in **both** the 360 zone (`zm_transit`) and the
  genuine **Wii U** zone (`mp_raid_genuine`).
- Comparing shader-name sets of 360 `common_mp` vs Wii U `mp_raid_genuine` (different maps) already
  yields **117 shared** `pimp_shader_*` names; a same-map pair (`common_mp` exists on both) will
  share far more.

These give a Xenos→R700 translator **ground-truth pairs**: for each shared hash you have the Xenos
microcode *and* the correct GX2 R700 microcode side by side to validate against.

---

## Verdicts

**360 → Wii U: plausible, at the recompile/transpile level — NOT byte-portable.**
- Same vendor (AMD/ATI), same architectural family (clause-based unified-shader VLIW), same
  big-endian container conventions, and confirmed matched source shaders on both.
- But the instruction encodings differ (Xenos vfetch/CF vs R700 TeraScale ALU/CF). You cannot copy
  bytes. A converter must either (a) decode Xenos microcode → re-encode R700 GX2 microcode, or
  (b) better, recover a common IR / the original HLSL-equivalent and recompile with GX2 shader tools,
  then wrap in the GX2 struct this project already knows how to emit (`shader_probe.py` layout).

**PS3 → Wii U: not viable.** Different GPU vendor and unrelated ISA. Do not chase this.

## Bottom line for the DLC port

Yes — **360 fastfiles are a workable shader source for DLC maps that lack a genuine Wii U version.**
The path is a **Xenos → R700/GX2 shader recompiler**, not a byte copy. It is a real, self-contained
engineering task (own ISA decode + GX2 encode), but it is de-risked by two things this scouting
confirmed: (1) both targets are the same AMD clause-based family, and (2) 100+ matched
same-source shader pairs already exist to validate the converter end-to-end. The GX2 output wrapper
is already solved in `wiiu_ref/shader_probe.py`.

### What a follow-up task would need
1. Xenos microcode decoder (CF/exec + vfetch + ALU/tex clauses → instruction list).
2. R700/TeraScale encoder, or reuse of an existing open GX2/R700 assembler (e.g. `latte-assembler`
   from decaf/Cemu tooling).
3. Validation harness over the matched-hash pairs (start with `transformonly_d4f4e04b`, then the
   `lmap_*` set — 117+ pairs available) comparing regenerated GX2 microcode to genuine Wii U.
4. Emit via the known 308 B VS / 232 B PS GX2 structs + FOLLOW microcode (already documented).

*(No files in the game folders / reference sets were modified. PS3 decompression is a gap in the
current Unlinker but does not change the verdict.)*
