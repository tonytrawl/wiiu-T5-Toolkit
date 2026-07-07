# WP-E findings: GX2/Latte GfxPackedVertex encoding (task #19, section 0p material)

Status: SOLVED and verified. Encoder/decoder: `wiiu_ref/latte_vertex.py`.
Genuine sample: `wiiu_ref/console_latte_vertex_sample.bin`
(mp_raid `ma_patio_heater_clean` surface 0, vc=546: 13104 bytes of verts0
followed by 4368 bytes of verts1).

## The split

The 32-byte PC GfxPackedVertex
(xyz f32x3 @0, binormalSign f32 @12, color u32 @16, texCoord u32 @20,
normal u32 @24, tangent u32 @28, all little-endian, normal/tangent in the
T6 "ThirdBased" 10-10-10 packing)
becomes TWO console streams per XSurface (both already located by the
solved console XSurface 128 layout: verts0 at +52, verts1 at +72).

### verts0, 24 bytes per vertex (geometry stream)

| off | size | field        | encoding                                        |
|-----|------|--------------|-------------------------------------------------|
| 0   | 12   | position     | 3 x BE float32. Exactly PC xyz, 4-byte-swapped. |
| 12  | 6    | normal       | 3 x BE snorm16, s16 = trunc(n * 32768), clamp [-32768,32767]. Decode n = s16 / 32768. Unit-length input. |
| 18  | 2    | binormalSign | BE snorm16. +1.0 -> 0x7FFF, -1.0 -> 0x8000. Only these two values occur in 322k genuine verts. |
| 20  | 3    | tangent      | 3 x snorm8, s8 = trunc(t * 128), clamp [-128,127]. Decode t = s8 / 128. Unit-length input. |
| 23  | 1    | pad          | Always 0x00 (322k/322k).                        |

GX2 fetch view: R32G32B32_FLOAT + R16G16B16A16_SNORM (normal.xyz,
binormalSign.w) + R8G8B8A8_SNORM (tangent.xyz, 0.w).

### verts1, 8 bytes per vertex (material stream, console-only second stream)

| off | size | field    | encoding                                              |
|-----|------|----------|-------------------------------------------------------|
| 0   | 4    | texCoord | 2 x BE float16, order (u, v). u = low 16 bits of the PC texCoord u32, v = high 16 bits. Same half-float bit patterns, no requantization. |
| 4   | 4    | color    | 4 x u8 in byte order r,g,b,a. Byte-identical to the PC GfxColor u32 stored little-endian (straight 4-byte copy, no swap). |

GX2 fetch view: R16G16_FLOAT + R8G8B8A8_UNORM.

So console 24 + 8 = 32 bytes total; nothing is added or lost versus PC
except normal/tangent precision, which is HIGHER on console for the normal
(16 bit vs PC 10 bit) and lower for the tangent (8 bit vs 10 bit).

## Quantizer details (matters for byte-exact writes)

- The truncation is toward zero: s = (int)(x * 32768.0f) and
  (int)(x * 128.0f) with clamping. Evidence: +1 -> 32767/127 (clamped),
  -1 -> -32768/-128, and both -127 (0x81) and -128 (0x80) occur in genuine
  tangents; only /128 decode + trunc*128 encode round-trips every genuine
  value byte-exact. Ranking on the mp_raid Rosetta: trunc*32768 beats
  floor*32767.5, floor*32768 and round*32767 for the normal; trunc*128
  beats round*127, floor*127.5, floor*128 for the tangent.
- decode(encode(x)) and encode(decode(s)) are exact inverses for all
  representable values (both scales are powers of two).

## What is and is not byte-exact when transcoding PC -> console

Exactly derivable from PC data (verified 100% on both Rosetta pairs):
position, texCoord, color, binormalSign, the pad byte.

NOT always byte-exact: normal and tangent. The original console linker
quantized from full-precision source floats; PC's 10-10-10 packing is
lossier (10-bit step about 0.004) than console snorm16, so the information
is simply not present in the PC zone. Re-encoding normalize(PC 10-bit
decode) with the trunc rule gives:
- mp_raid pair (741 aligned surfaces, 196581 verts): normal16 19.07% exact,
  tangent8 46.09% exact, everything else 100%, whole vertex 14.74%,
  53/741 surfaces fully byte-exact.
- zm_transit vs PC zm_nuked (137 shared surfaces, 57359 verts): normal16
  29.63%, tangent8 62.11%, whole vertex 24.86%, 18/137 surfaces fully
  byte-exact.
All non-exact normals/tangents are within 1-2 quantizer steps (max
direction error < 0.002, i.e. sub-10-bit); an interval-consistency test
with the PC 10-bit quantization bounds shows zero violations for the
normal. For rendering this is exact-to-the-source-precision; a Wii U map
built from PC data will shade identically to within PC's own 10-bit
precision.

Known content (not encoding) divergences found by the Rosetta: 11/741
mp_raid surfaces have genuinely different UVs on Wii U (4 beach sandals, 2
mural paintings, prague_china_plates_stand_red), and
prague_china_plates_stand_red also has regenerated tangents.

## Verification protocol run

`python wiiu_ref/latte_vertex.py` performs, and passed:
1. Decode -> floats -> re-encode identity, byte-exact, on every inline
   verts0/verts1 vertex in TWO genuine zones: mp_raid_genuine.zone
   (789 surfaces, 211044 verts) and zm_transit_original.zone (285
   surfaces, 110948 verts). 0 mismatches, pad always 0, binormalSign
   always +-1, all normals unit length.
2. PC -> console re-encode scored against genuine bytes on surfaces
   aligned by full position-content match (mp_raid pair: 741 surfaces;
   zm_transit vs zm_nuked: 137 surfaces), numbers above.

The surface aligner uses the solved console XModel/XSurface walk from
`xmodel_probe.py` (static surfaces only; skinned surfaces are skipped until
WP-A lands, but the vertex format itself is the same 24-byte verts0).

## Implications

- Task #19 unblocked: PC verts0 can be transcoded to console verts0+verts1
  with `pc_vertex_to_console()`; the reverse path `console_vertex_to_pc()`
  reconstructs a valid PC GfxPackedVertex (repacking the unit frame *2 into
  the ThirdBased 10-10-10, matching the genuine PC convention of storing
  length-2 packed vectors).
- The same 24-byte verts0 format underlies skinned surfaces (WP-A), and
  GfxWorld's vertexData streams likely reuse the same primitive encodings
  (BE f32 / BE snorm16 / snorm8 / BE f16 / raw color bytes); check GfxWorld
  vd0/vd1 against this table when WP-B lands.
