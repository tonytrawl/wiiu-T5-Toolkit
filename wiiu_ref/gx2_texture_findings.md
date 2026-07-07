# WP-F findings: GX2 texture de-tiling and swizzle (2026-07-04)

Deliverable: `wiiu_ref/gx2_texture.py` (detile()/tile() plus the verification
harness; run `python wiiu_ref/gx2_texture.py` with no args to reproduce every
number below). Genuine tiled samples: `console_gx2_tiled_sample_tm2.bin`
(wiiu_dpad_up, 64x64 BC3 tileMode 2, full 328 B GfxImage body + name + 0x2000
pixel bytes, cut from common_mp.zone at 0x50577d) and
`console_gx2_tiled_sample_tm4.bin` (wiiu_controller_icon_drc, 128x128 BC3
tileMode 4 with 8 mips, cut at 0x4a1a7d, 0x8000 pixel bytes).

Do not merge into WIIU_UNLINK_STATUS.md yet; this file is the WP-F output for
the later merge pass.

## 1. What the corpus actually contains

Scanned every console GfxImage body (section 0f layout) in the three genuine
zones. All inline (non-streamed) images, 812 total with pixel data:

| zone | bodies | inline with pixels |
|---|---|---|
| common_mp.zone (root) | 532 | 532 |
| wiiu_ref/mp_raid_genuine.zone | 78 | 78 |
| wiiu_ref/zm_transit_original.zone | 202 | 202 |

Only TWO tile modes occur anywhere: 2 (GX2_TILE_MODE_1D_TILED_THIN1, micro
tiled) and 4 (GX2_TILE_MODE_2D_TILED_THIN1, macro tiled). aa=0 everywhere.
Formats: BC1 0x31, BC2 0x32, BC3 0x33, BC5 0x35, RGBA8 0x1a, R8 0x01,
R5G6B5 0x07. Three images are cube maps (dim=3, depth=6, the `*_ft` skybox
and reflection images); everything else is dim=1 2D. The streamed (IPAK) map
images carry the same GX2Texture header fields, so the same math applies to
IPAK pixel payloads.

Swizzle field values seen: 0x00000 (all tileMode 2), and 0x10000 / 0x20000 /
0x30000 / 0xd0000 (tileMode 4). Bits 8..10 (the bank/pipe swizzle the
hardware actually applies, pipe = (swizzle>>8)&1, bank = (swizzle>>9)&3) are
ZERO in every case; the bits at 16+ are the GX2 address-alias id and do not
affect the byte layout. Confirmed by content: de-tiling with bank/pipe
swizzle 0 reconstructs recognizable images regardless of the high bits.

## 2. The mapping (Latte / GPU7 addrlib, thin, aa=0, not depth)

Parameters: 2 pipes, 4 banks, pipe interleave 256 B, row size 2048 B, split
size 2048 B. Element = pixel, or one 4x4 block for BCn (dims divide by 4,
bpp becomes 64 for BC1/BC4 and 128 for BC2/3/5).

Element sizes seen: 8 bpp (R8), 16 (565), 32 (RGBA8), 64 (BC1), 128
(BC2/BC3/BC5).

### Micro tile interior (both tile modes)
8x8 elements per micro tile. Element index inside the tile, from x0=x&1,
x1=(x>>1)&1, x2=(x>>2)&1, y0, y1, y2 likewise; bit order LSB first:

| bpp | index bits (LSB..MSB) |
|---|---|
| 8   | x0 x1 x2 y1 y0 y2 |
| 16  | x0 x1 x2 y0 y1 y2 |
| 32  | x0 x1 y0 x2 y1 y2 |
| 64  | x0 y0 x1 x2 y1 y2 |
| 128 | y0 x0 x1 x2 y1 y2 |

### tileMode 2 (1D micro tiled)
```
microTileBytes = 64 * bpp / 8
addr = microTileBytes * ((x>>3) + (y>>3) * (pitch>>3))
     + pixelIndex * bpp / 8
```

### tileMode 4 (2D macro tiled thin1)
Macro tile = 4 banks x 2 pipes of micro tiles = 32x16 elements.
```
pipe = ((y>>3) ^ (x>>3)) & 1
bank = ((y>>5) ^ (x>>3)) & 1  |  2 * (((y>>4) ^ (x>>4)) & 1)
bankPipe = (pipe + 2*bank) ^ ((pipeSwz + 2*bankSwz + slice*rotation) & 7)
           (rotation = 2 for tileMode 4..11; slice = cube face index)
pipe = bankPipe & 1 ; bank = bankPipe >> 1
macroTileBytes  = bpp * 16 * 32 / 8
macroTileOffset = ((x>>5) + (pitch>>5) * (y>>4)) * macroTileBytes
total = pixelIndex * bpp / 8  +  macroTileOffset >> 3
addr  = bank<<9 | pipe<<8 | (total & 255) | (total & ~255) << 3
```
i.e. bytes interleave in 256-byte groups: group index bits get the pipe bit
at position 8 and the two bank bits at 9..10.

### Surface padding (matches every stored pitch and imageSize, 812/812)
- tileMode 2: pitchAlign = max(8, 256/bpp) elements, heightAlign = 8,
  baseAlign = 256.
- tileMode 4: pitchAlign = max(32, 32 * (256/bpp/8)) elements (so 32 for
  bpp>=32, 64 for 16 bpp, 128 for 8 bpp), heightAlign = 16,
  baseAlign = max(macroTileBytes, pitchAlign * 16 * bpp / 8).
- imageSize = paddedPitch * paddedHeight * bpp/8 (times 6 for cube level 0).
- GX2Texture.pitch is stored in ELEMENTS (blocks for BCn) and equals the
  padded pitch.

### Mip chain (matches every stored mipLevelOffset word, all 812)
Level dims: max(1, w>>level) then nextPow2 (level >= 1). A tileMode 4 level
drops to tileMode 2 when its padded width < widthAlignFactor*32 or height <
16 elements, where widthAlignFactor = max(1, 256/microTileBytes) (1 for
BCn/RGBA8, 4 for R8, 2 for 565). Offsets: mipLevelOffset[0] = offset of
level 1 from the IMAGE BASE = imageSize (the mip buffer is appended
directly); mipLevelOffset[i>=1] = offset of level i+1 from the MIP BUFFER
start; levels are laid contiguously, each aligned to its level baseAlign.
mipSize = total mip buffer size, also matches. Cube maps pad the slice count
to nextPow2(6) = 8 on mip levels but store 6 faces at level 0.

### Cube maps (dim=3)
imageSize = 6 * per-face size; faces are stored consecutively; the face
index enters the bank/pipe XOR as slice*2 (rotation 2). Verified byte-exact
on all 3 cube images including whitesquare_ft (tileMode 2, where the face
index does not affect intra-face layout) and skybox_mp_overflow_ft
(512x512 BC3 tileMode 4).

## 3. Verification performed (all reproducible via the harness)

1. Structural: recomputed pitch, imageSize, effective tile mode, all
   mipLevelOffset words and mipSize for every inline image and required
   exact equality with the stored GX2Texture words: 812/812 pass.
2. Bijection: the address map over the padded grid is a byte-exact
   permutation of [0, imageSize) for every image (no collision, no gap):
   812/812.
3. Round trip: detile() then tile() reproduces the genuine tiled bytes
   byte-exact: 812/812 (and per cube face on the 3 cube maps).
4. Content (rules out a self-consistent but wrong permutation, which checks
   1-3 cannot): decoded detiled surfaces to PNG and confirmed recognizable
   content: wiiu_tv (RGBA8 tm4, clean TV icon), wiiu_controller_icon_drc
   (BC3 tm4, GamePad icon; mips 1..7 all decode as clean downscales,
   including the tm4 -> tm2 degraded levels), wiiu_dpad_up / grenadepointer /
   devgui_mouse_pointer (BC3 tm2), compassping_enemysatellite_diamond_top
   (BC1 tm4), fxt_light_ray_solid (R8 tm4), fxt_mov_smk_scattered (565 tm4,
   spatially coherent).

No PC linear copy of these images exists in the local PC zones (PC BO2
streams them from its own IPAK), so cross-platform byte comparison was not
possible; the content check above stands in for it.

## 4. Write direction (PC -> Wii U transcode recipe)

For a linear PC DXT/RGBA surface: pick tileMode (stock linker behavior: 4,
dropping to 2 when the padded surface is smaller than one macro tile, which
reproduces every tileMode choice seen in the corpus), compute pitch/height
padding per section 2, pad_linear() the rows, then tile(). Set swizzle to 0
(bank/pipe bits; the 0x10000-style high bits are cosmetic address-alias ids;
stock zones use 0xd0000 for mipless tm4 images and 0x10000/0x20000/0x30000
for mipped ones, exact rule unconfirmed and apparently inert). Build
mipLevelOffset with mip_chain(). BCn block bytes are stored in the same
little-endian order as PC DDS data; no byte swap inside elements (confirmed
visually for BC1/BC3/RGBA8; 16-bit 565 assumed LE, only spatial coherence
confirmed).

## 5. Open ends

- 16-bit element byte order only verified as spatially coherent, not against
  a linear reference (no 565 reference available locally).
- IPAK-streamed map textures: same header math applies but the IPAK
  container itself was out of scope here.
- Tile modes other than 1/2/3/4 (bank-swapped 8..11, thick, aa>0) are not
  needed by the corpus and are unimplemented; detile/tile raise KeyError or
  produce garbage for them by design.
- Shader microcode transcode (the second half of WP-F) untouched;
  the stock-shader-by-name shortcut remains the plan.
