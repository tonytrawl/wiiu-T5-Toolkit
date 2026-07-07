#!/usr/bin/env python3
"""
Material PC(v147, LE) -> console(WiiU v148, BE) body converter  (HANDOFF Track A).

Material is NOT a clean byte-swap: the console struct is 104 B, the PC struct 112 B.
The console layout drops the fields that only exist for the D3D11 runtime:

  divergence (verified against genuine common_mp via a matched-pair oracle — 437/446 shared
  materials convert byte-exact; see validate_material.py):
    * MaterialInfo   48 -> 40 B   : drops `surfaceFlags` (u32 @ PC off 36) + trailing pad;
                                    `contents` (PC @40) moves to console @36 and is copied
                                    VERBATIM (the linker does NOT byte-swap it). drawSurf IS kept
                                    (8-byte-swapped as a packed u64). All other scalars byte-swap.
    * stateBitsEntry char[36] -> char[32] : mirrors MaterialTechniqueSet.techniques 36 -> 32
                                    (per-technique state-bits index; console technique enum is a
                                    32-slot reordered subset of PC's 36 — a raw truncation, adequate
                                    for shared materials; full slot remap is shared with Track B).
    * GfxStateBits   20 -> 8 B    : keeps loadBits[2]; drops the 3 D3D state-object pointers
                                    (blendState/depthStencilState/rasterizerState, ZoneCode
                                    condition = never).
    * Material total 112 -> 104 B : counts move 84 -> 72, the 5 pointers 92 -> 80.
  KNOWN GAP: 9/446 "mc/mtl_*" model materials with a non-zero hashIndex/surfaceFlags packing
  diverge in the 2 bytes @ console off 34 — not yet reversed (low impact; hashIndex is a sort hash).

Trailing dynamic data (console stream order, after the 104 B body):
    info.name c-string, then textureTable[textureCount] (MaterialTextureDef, 16 B, image ptr @12),
    constantTable[constantCount] (MaterialConstantDef, 32 B, nameHash + name[12] + vec4 literal),
    stateBitsTable[stateBitsCount] (GfxStateBits -> 8 B loadBits), then (if thermalMaterial FOLLOWs)
    an inline thermal Material.  techniqueSet / thermalMaterial / textureDef.image are asset refs
    (alias or FOLLOW-to-inline); pointer values are remapped through `reloc`.

`reloc(pc_ptr_value) -> console_ptr_value` handles the alias relocation (omap) at integration
time; FOLLOW/INSERT/null are always preserved verbatim.  The default identity reloc is only for
the self-contained round-trip test.
"""
import struct

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)

PC_MAT_SIZE = 112
CO_MAT_SIZE = 104
PC_SB_SIZE = 20          # GfxStateBits on PC
CO_SB_SIZE = 8           # GfxStateBits on console (loadBits[2] only)
TEXDEF_SIZE = 16
CONSTDEF_SIZE = 32


def _default_reloc(v):
    return v


PC_IMG_BODY = 64
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'wiiu_ref'))
import ipak as _IP


class ImageSpanFail(Exception):
    pass


def pc_image_span(d, off, window=20):
    """End offset of one inline PC GfxImage that begins at `off` (right after a material texdef whose
    image ptr FOLLOWs). DETERMINISTIC — NOT a hash search (that failed on images with comma-prefixed
    aliased names whose hash@+60 is 0). The GfxImage body sits after a fixed lead (0 or 16 B) and is
    identified by its name-ptr FOLLOW @+56 within a TINY window (so the scan can't run into the next
    asset on dense zones). Then structurally: the reorder emits the inline name string (may carry a
    leading ',' alias marker — kept verbatim to its NUL), then texture.loadDef = a GfxImageLoadDef
    12-B header (levelCount@0/flags@1/format@4/resourceSize@8) + resourceSize pixel bytes (streamed
    images have resourceSize=0 -> a bare 12-B tail; inline-pixel images carry real pixels)."""
    for b in range(off, off + window, 4):
        if b + PC_IMG_BODY > len(d):
            break
        if struct.unpack_from('<I', d, b + 56)[0] != FOLLOW:      # image body's name ptr @+56
            continue
        e = d.index(b'\x00', b + PC_IMG_BODY, b + PC_IMG_BODY + 160)   # inline name string
        o = e + 1
        # texture.loadDef tail is emitted only for REAL inline images (texture/loadDef ptr @body+0
        # non-zero). Aliased stubs (comma-prefixed name, zeroed body, texture@0==0) carry no loadDef.
        if struct.unpack_from('<I', d, b + 0)[0] != 0:
            resource_size = struct.unpack_from('<I', d, o + 8)[0]  # GfxImageLoadDef.resourceSize
            o += 12 + resource_size
        return o
    # No inline-name landmark: a NULL-name streamed image (name@+56 not FOLLOW — the image name is
    # aliased/null, common for top-level-material textures). Body is a plain 64-B GfxImage at `off`;
    # texture.loadDef pixels only if texture@0 is FOLLOW (INSERT/alias -> referenced, no inline data).
    # NULL-name streamed inline image (PC streams pixels; console inlines them). Empirical formula:
    #   span = body(64) + streamedPartCount×GfxStreamedPartInfo(8) + GfxImageLoadDef(12 header +
    #   resourceSize, resourceSize=0 for streamed). streamedPartCount is the byte @27 (struct_layout
    #   GfxImage is the WRONG variant for these — its offsets don't apply; pinned empirically).
    if off + PC_IMG_BODY > len(d):        # truncated buffer (e.g. isolated round-trip test)
        return min(off + PC_IMG_BODY, len(d))
    o = off + PC_IMG_BODY + d[off + 27] * 8
    if struct.unpack_from('<I', d, off + 0)[0] in PTRS:         # texture.loadDef present
        rs = struct.unpack_from('<I', d, o + 8)[0]
        o += 12 + (rs if 0 <= rs < 0x8000000 else 0)           # resourceSize (guard garbage)
    return o


# ---- little helpers over a source buffer with a chosen endianness ----
def _u32(buf, o, le):
    return struct.unpack_from('<I' if le else '>I', buf, o)[0]

def _swap32(buf, o):
    """read LE u32 at o -> BE bytes (and vice-versa; symmetric)."""
    return struct.pack('>I', struct.unpack_from('<I', buf, o)[0])


# =====================================================================
# forward: PC (LE) material body -> console (BE) bytes
# =====================================================================
def convert_material(pc, off, reloc=_default_reloc):
    """Convert one PC material at stream offset `off`. Returns (console_bytes, next_pc_off).
    `console_bytes` is the full console material region (104 B body + trailing dynamic data)."""
    out = bytearray()

    # ---- MaterialInfo 48 -> 40 : drops `surfaceFlags` (PC u32 @36) + trailing pad; `contents`
    #      (PC @40) moves to console @36. drawSurf IS kept. (verified vs genuine common_mp
    #      matched-pair oracle: console@36 == PC contents@40.) ----
    out += struct.pack('>I', reloc(_u32(pc, off + 0, True)))      # name ptr
    out += _swap32(pc, off + 4)                                   # gameFlags
    out += pc[off + 8: off + 16]                                  # pad/sortKey/atlas + pad (bytes)
    out += struct.pack('>Q', struct.unpack_from('<Q', pc, off + 16)[0])  # drawSurf (packed u64)
    out += _swap32(pc, off + 24)                                  # surfaceTypeBits
    out += _swap32(pc, off + 28)                                  # layeredSurfaceTypes
    out += struct.pack('>H', struct.unpack_from('<H', pc, off + 32)[0])  # hashIndex u16
    out += pc[off + 34: off + 36]                                 # pad (2)
    out += pc[off + 40: off + 44]                                 # contents (-> console @36) — VERBATIM,
    #   the linker does NOT byte-swap this field (525/0 across the matched-pair oracle).
    # PC surfaceFlags @36..39 + pad @44..47 dropped

    # ---- stateBitsEntry char[36] -> char[32] ----
    out += pc[off + 48: off + 48 + 32]

    # ---- counts / flags (6 bytes) @84 -> @72 ----
    texc, constc, sbc = pc[off + 84], pc[off + 85], pc[off + 86]
    out += pc[off + 84: off + 90]
    out += b'\x00' * 2                                            # pad -> pointers @80

    # ---- 5 pointers @92 -> @80 ----
    ts  = _u32(pc, off + 92, True)
    tt  = _u32(pc, off + 96, True)
    ct  = _u32(pc, off + 100, True)
    sbt = _u32(pc, off + 104, True)
    th  = _u32(pc, off + 108, True)
    for v in (ts, tt, ct, sbt, th):
        out += struct.pack('>I', reloc(v))
    out += b'\x00' * 4                                            # tail pad -> 104
    assert len(out) == CO_MAT_SIZE, len(out)

    src = off + PC_MAT_SIZE

    # ---- trailing dynamic data, console stream order ----
    # info.name c-string
    if (ts, tt, ct, sbt, th) and _u32(pc, off + 0, True) in PTRS:
        end = pc.index(b'\x00', src)
        out += pc[src:end + 1]
        src = end + 1

    # textureTable[textureCount] : MaterialTextureDef 16 B (identical size)
    if tt in PTRS:
        inline_imgs = []
        for i in range(texc):
            base = src + i * TEXDEF_SIZE
            out += _swap32(pc, base + 0)              # nameHash
            out += pc[base + 4: base + 12]            # nameStart/End, samplerState, semantic, isMature, pad
            imgv = _u32(pc, base + 12, True)
            out += struct.pack('>I', reloc(imgv))     # image ptr
            if imgv in PTRS:
                inline_imgs.append(i)
        src += texc * TEXDEF_SIZE
        # inline images (image ptr FOLLOW): consume their PC span so `src` stays correct. The
        # console GfxImage (328 B) differs from PC (64 B) — the byte CONVERSION of inline images is
        # the image-converter's job (TODO); here we only advance past them so the walk resyncs.
        # Best-effort: if a landmark isn't found (inline-pixel variants not yet fully reversed),
        # stop advancing rather than raise — Track A's is_pure filter excludes inline-image
        # materials from byte validation, so this only affects the traversal span for those.
        for _ in inline_imgs:
            try:
                src = pc_image_span(pc, src)
            except ImageSpanFail:
                break

    # constantTable[constantCount] : MaterialConstantDef 32 B (identical size)
    if ct in PTRS:
        for i in range(constc):
            base = src + i * CONSTDEF_SIZE
            out += _swap32(pc, base + 0)              # nameHash
            out += pc[base + 4: base + 16]            # name char[12] verbatim
            for w in range(4):                        # literal vec4 (4 floats)
                out += _swap32(pc, base + 16 + w * 4)
        src += constc * CONSTDEF_SIZE

    # stateBitsTable[stateBitsCount] : GfxStateBits 20 -> 8 (loadBits[2] only)
    if sbt in PTRS:
        for i in range(sbc):
            base = src + i * PC_SB_SIZE
            out += _swap32(pc, base + 0)              # loadBits[0]
            out += _swap32(pc, base + 4)              # loadBits[1]
        src += sbc * PC_SB_SIZE

    # thermalMaterial (inline) — recurse
    if th in PTRS:
        sub, src = convert_material(pc, src, reloc)
        out += sub

    return bytes(out), src


# =====================================================================
# inverse: console (BE) material body -> PC (LE) bytes.  For the self-contained
# round-trip test only (re-inserts drawSurf zeros, expands stateBitsEntry/GfxStateBits).
# =====================================================================
def deconvert_material(co, off, reloc=_default_reloc):
    """console material @off -> (pc_bytes_LE, next_co_off)."""
    out = bytearray()
    def be32(o): return struct.unpack_from('>I', co, o)[0]
    def put_le(v): out.extend(struct.pack('<I', v))

    # MaterialInfo 40 -> 48 (same offsets; re-append dropped contents=0 + pad)
    put_le(reloc(be32(off + 0)))                     # name
    put_le(be32(off + 4))                            # gameFlags
    out += co[off + 8: off + 16]                     # pad/sortKey/atlas + pad
    out += struct.pack('<Q', struct.unpack_from('>Q', co, off + 16)[0])  # drawSurf
    put_le(be32(off + 24))                           # surfaceTypeBits
    put_le(be32(off + 28))                           # layeredSurfaceTypes
    out += struct.pack('<H', struct.unpack_from('>H', co, off + 32)[0])  # hashIndex
    out += co[off + 34: off + 36]                    # pad
    out += b'\x00' * 4                               # surfaceFlags (dropped on console) = 0
    out += co[off + 36: off + 40]                    # contents (console @36 -> PC @40) — VERBATIM
    out += b'\x00' * 4                               # MaterialInfo pad -> 48

    # stateBitsEntry char[32] -> char[36]
    out += co[off + 40: off + 40 + 32]
    out += b'\x00' * 4

    texc, constc, sbc = co[off + 72], co[off + 73], co[off + 74]
    out += co[off + 72: off + 78]                    # counts/flags
    out += b'\x00' * 2                               # pad -> pointers @92

    ts, tt, ct, sbt, th = (be32(off + 80), be32(off + 84), be32(off + 88),
                           be32(off + 92), be32(off + 96))
    for v in (ts, tt, ct, sbt, th):
        put_le(reloc(v))
    assert len(out) == PC_MAT_SIZE, len(out)

    src = off + CO_MAT_SIZE
    if be32(off + 0) in PTRS:
        end = co.index(b'\x00', src)
        out += co[src:end + 1]; src = end + 1
    if tt in PTRS:
        for i in range(texc):
            base = src + i * TEXDEF_SIZE
            put_le(be32(base + 0))
            out += co[base + 4: base + 12]
            put_le(reloc(be32(base + 12)))
        src += texc * TEXDEF_SIZE
    if ct in PTRS:
        for i in range(constc):
            base = src + i * CONSTDEF_SIZE
            put_le(be32(base + 0))
            out += co[base + 4: base + 16]
            for w in range(4):
                put_le(be32(base + 16 + w * 4))
        src += constc * CONSTDEF_SIZE
    if sbt in PTRS:
        for i in range(sbc):
            base = src + i * CO_SB_SIZE
            put_le(be32(base + 0)); put_le(be32(base + 4))
            out += b'\x00' * 12                       # drop D3D state pointers
        src += sbc * CO_SB_SIZE
    if th in PTRS:
        sub, src = deconvert_material(co, src, reloc)
        out += sub
    return bytes(out), src
