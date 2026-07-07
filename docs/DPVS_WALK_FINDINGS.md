# GfxWorld dpvs walker — FINDINGS (2026-07-05)

## Bottom line
**The task premise is disproven.** The genuine walk does NOT desync in the dpvs — it desyncs
much earlier, inside the **draw** section. The "dpvs arrays start" anchor (0x3536c79) that all
prior dpvs work used actually points INSIDE the genuine worldVd vertex buffer (vd0). The
"36-byte drawinst-like records" seen there are **worldVd vertices** (pos3f + binormal-sign
±1.0f + RGBA color + f16 UVs, 36 B/vertex; vertexCount 162,752 × 36 ≈ vd0 size 5,860,976 ✓).

## Hard numbers
- Genuine GfxWorld: 0x2b7029d → 0x40aa61d = **22,258,560 B**.
- Our converted GfxWorld (mp_raid_rewrite.ff): 0x3fcdd15 → 0x4e20b97 = **15,019,650 B**.
- **Genuine carries ~7.24 MB of console-only data our writer never emits.**
- Siege-skin shader tail verified: genuine @0x40a7ad0..0x40aa61d (11,085 B, byte-equal to
  `SIEGE_SKIN_TAIL`), ends EXACTLY at GameWorldMp. Occluders x5 (340 B) directly before it.

## Where the desync actually is
The section walk (gfxworld_probe.py / probe2 / our write path) is correct up through the
**cells** (0x2bb01b5). It goes wrong inside **GfxWorldDraw**:

1. After the 29 reflection-probe bodies, genuine has per-probe dynamics (probeVolumes,
   marker+count 0x28 seen @0x2bb0a51) **plus inline GX2 pixel data**. From ~0x2bb0ba1 to
   ~0x3238xxx there are **~6.85 MB of DXT/BC-compressed texture blocks** (0xAAAA index
   patterns, entropy 3.5–6.0): reflection-probe cubemaps + lightmap pixels, stored in-zone
   ("gump" data). `consume_image` (and our writer) emit only the 328-B image body — none of
   the pixels.
2. True vd0 (worldVd, 5,860,976 B of 36-B vertices) begins ~0x3238–0x3239xxxx, i.e. ~6.85 MB
   later than the probe placed it. Everything downstream (vd1, indices, lightGrid, models,
   dpvs, tail) shifts accordingly. All prior "byte-match" claims for post-draw sections were
   comparing misattributed offsets (e.g. the "models/materialMemory/outdoorImage" bytes at
   0x3535fxx are mid-vertex-buffer garbage).
3. Additionally ~4 MB of post-vd0 console-only lighting data exists (f16 UV pair tables,
   RGB/RGBA color tables, s16 normal tables, zero bitmask pages between ~0x37d0000 and
   ~0x40a0000) that the PC-derived model has no fields for — genuine console smodel/surface
   vertex lighting.

## Why this explains the crash
The Wii U crash is a heap overrun in `DB_GumpShouldFree`. **Gumps are exactly the console
in-zone pixel/lighting allocations** this missing data feeds. Our GfxWorld ships without the
inline gump payloads the console loader expects to walk/free → allocator walks garbage →
heap overrun. This is a *content/format gap*, not a small size/count bug in
`Write_GfxWorldDpvsStatic`; there is no one-line writer fix.

## Recommendation
Commit to the **genuine-GfxWorld INLINE path** (transplant the genuine mp_raid GfxWorld
stream wholesale, as already done for GameWorldMp/MapEnts), rather than trying to synthesize
the ~11 MB of console gump/lighting/probe-pixel data the PC zone doesn't contain. If a
synthesized GfxWorld is ever needed for *custom* maps, the work items are:
1. Reverse the console GfxImage inline-pixel (gump) encoding after each probe/lightmap image
   body (start @0x2bb0ba1; 29 probe images + lightmaps ≈ 6.85 MB).
2. Reverse the post-vd0 lighting tables (~4 MB @0x37d0000..0x40a0000).
3. Only then re-derive the true dpvs static array layout (it lives ~0x3bd0000+, not
   0x3536c79; console element sizes there remain unverified).

## Tooling
- `wiiu_ref/dpvs_walk_full.py` — full write-path model walker (dpvs static + dyn + trailing
  sections + siege tail + inline-Material consumption via walker.py). Works as designed; it
  undershoots on genuine by ~10.4 MB, which is what exposed the misanchor.
- Key probes used: ±1.0f binormal-column scan (vd0 extent), FFFFFFFF stride histogram,
  entropy/DXT scan, siege-tail byte match.
