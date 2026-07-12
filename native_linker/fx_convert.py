#!/usr/bin/env python3
"""
FX (FxEffectDef) PC(LE) -> console(BE) converter  (HANDOFF Track D).

FxEffectDef (76 B) and FxElemDef (292 B) are byte-IDENTICAL in layout on PC and console, so the
converter is a straight per-field byte-swap + pointer-relocate — verified against genuine common_mp
(388 matched-by-name pairs): the header has NO verbatim-float quirks (unlike Material `contents` /
XModel `lightingOrigin`); the count fields are u16 (a 4-byte swap of the flags/count words is wrong,
they must swap at u16 granularity), and `totalSize` swaps cleanly (388/0) so it is derivable, not a
console-computed value.

This module converts the 76-B FxEffectDef HEADER (validated byte-exact). The FxElemDef array (292 B
each) + dynamic tail (velSamples/visSamples curves, visuals, refs) reuse `fx_pc.parse_fx_pc`'s
traversal for extents and the same per-field swap methodology — TODO, tracked in the handoff.
"""
import struct

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)
FX_HDR = 76


def _default_reloc(v):
    return v


def _sw16(pc, o):
    return struct.pack('>H', struct.unpack_from('<H', pc, o)[0])

def _sw32(pc, o):
    return struct.pack('>I', struct.unpack_from('<I', pc, o)[0])


def convert_fx_header(pc, off, reloc=_default_reloc):
    """Convert the 76-B FxEffectDef header PC->console. Byte-exact vs genuine (388/388, masking the
    two relocated pointers)."""
    def ptr(o):
        return struct.pack('>I', reloc(struct.unpack_from('<I', pc, o)[0]))
    out = bytearray()
    out += ptr(off + 0)                    # name
    out += _sw16(pc, off + 4)              # flags (u16)
    out += pc[off + 6: off + 8]            # efPriority (u8) + pad
    out += _sw16(pc, off + 8)              # elemDefCountLooping (i16)
    out += _sw16(pc, off + 10)             # elemDefCountOneShot (i16)
    out += _sw16(pc, off + 12)             # elemDefCountEmission (i16)
    out += pc[off + 14: off + 16]          # pad
    out += _sw32(pc, off + 16)             # totalSize
    out += _sw32(pc, off + 20)             # msecLoopingLife
    out += _sw32(pc, off + 24)             # msecNonLoopingLife
    out += ptr(off + 28)                   # elemDefs
    for k in range(6):                     # boundingBoxDim vec3 + boundingBoxCentre vec3
        out += _sw32(pc, off + 32 + k * 4)
    out += _sw32(pc, off + 56)             # occlusionQueryDepthBias
    out += _sw32(pc, off + 60)             # occlusionQueryFadeIn
    out += _sw32(pc, off + 64)             # occlusionQueryFadeOut
    out += _sw32(pc, off + 68)             # occlusionQueryScaleRange.min (FxFloatRange)
    out += _sw32(pc, off + 72)             # occlusionQueryScaleRange.max
    assert len(out) == FX_HDR, len(out)
    return bytes(out)


# =====================================================================
# Full FxEffectDef converter: header + name + FxElemDef array + dynamic tail
# (layouts PC-identical per fx_probe/T6_Assets.h — per-field BE swap + reloc)
# =====================================================================
ED = 292

# FxElemDef field granularity (T6_Assets.h:5457). Everything is a 4-byte scalar
# except these:
_ELEM_CHARS = set(range(172, 178)) | set(range(184, 188)) | set(range(260, 264))
_ELEM_U16 = {178, 264, 266, 268, 270}
# pointer-valued u32 fields (relocated): velSamples/visSamples/visuals-union,
# effectOnImpact/Death/Emitted, effectAttached, extended, spawnSound
_ELEM_PTRS = {188, 192, 196, 224, 228, 232, 252, 256, 280}

TYPE_TRAIL = 5
TYPE_MODEL = 7
TYPE_SPOT_LIGHT = 9
TYPE_SOUND = 10
TYPE_DECAL = 11
TYPE_RUNNER = 12


class _Out:
    """BE emit buffer that records the output offsets of relocated (non-sentinel)
    pointers so an oracle diff can mask them."""
    def __init__(self, reloc):
        self.b = bytearray()
        self.reloc = reloc
        self.ptr_offs = []

    def ptr(self, pc, o):
        v = struct.unpack_from('<I', pc, o)[0]
        if v not in PTRS and v != 0:
            self.ptr_offs.append(len(self.b))
        self.b += struct.pack('>I', self.reloc(v))

    def sw32(self, pc, o, n=1):
        for k in range(n):
            self.b += _sw32(pc, o + 4 * k)

    def sw16(self, pc, o):
        self.b += _sw16(pc, o)

    def raw(self, pc, o, n):
        self.b += pc[o:o + n]

    def cstr(self, pc, o):
        e = pc.index(b'\x00', o)
        self.b += pc[o:e + 1]
        return e + 1


def _conv_elem_fixed(pc, eb, out):
    """One 292-B FxElemDef body: per-field swap at correct granularity."""
    out.sw32(pc, eb + 0, 43)               # flags..reflectionFactor (0..171, all 4-B scalars)
    out.raw(pc, eb + 172, 6)               # atlas: 6 chars
    out.sw16(pc, eb + 178)                 # atlas.entryCountAndIndexRange
    out.sw32(pc, eb + 180)                 # windInfluence
    out.raw(pc, eb + 184, 4)               # elemType/visualCount/velIC/visSIC
    out.ptr(pc, eb + 188)                  # velSamples
    out.ptr(pc, eb + 192)                  # visSamples
    out.ptr(pc, eb + 196)                  # visuals union
    out.sw32(pc, eb + 200, 6)              # collMins/collMaxs
    out.ptr(pc, eb + 224)                  # effectOnImpact
    out.ptr(pc, eb + 228)                  # effectOnDeath
    out.ptr(pc, eb + 232)                  # effectEmitted
    out.sw32(pc, eb + 236, 4)              # emitDist / emitDistVariance
    out.ptr(pc, eb + 252)                  # effectAttached
    out.ptr(pc, eb + 256)                  # extended
    out.raw(pc, eb + 260, 4)               # sortOrder/lightingFrac/unused[2]
    for o in (264, 266, 268, 270):         # alphaFadeTimeMsec..lifespanAtMaxWind (u16)
        out.sw16(pc, eb + o)
    out.sw32(pc, eb + 272, 2)              # FxElemDefUnion (billboard trim / cloud range)
    out.ptr(pc, eb + 280)                  # spawnSound
    out.sw32(pc, eb + 284, 2)              # billboardPivot


def _u32le(d, o):
    return struct.unpack_from('<I', d, o)[0]


def _conv_material_inline(pc, o, out):
    import material_convert as MC
    body, nxt = MC.convert_material(pc, o, out.reloc)
    out.b += body
    return nxt


def _conv_visual_dyn(pc, c, vptr, etype, out):
    if vptr not in PTRS:
        return c
    if etype in (TYPE_SOUND, TYPE_RUNNER):
        return out.cstr(pc, c)
    if etype <= 6:                         # sprite/tail/line/trail/cloud -> inline material
        return _conv_material_inline(pc, c, out)
    raise ValueError('inline visual asset (type %d) unsupported' % etype)


def _conv_elem_dyn(pc, eb, c, out):
    etype = pc[eb + 184]
    vcount = pc[eb + 185]
    vic = pc[eb + 186]
    vsc = pc[eb + 187]
    if _u32le(pc, eb + 188) in PTRS:       # velSamples: all-float 96-B samples
        n = (vic + 1) * 96
        out.sw32(pc, c, n // 4); c += n
    if _u32le(pc, eb + 192) in PTRS:       # visSamples: 2x FxElemVisualState(24) per sample
        for _ in range((vsc + 1) * 2):
            out.raw(pc, c, 4)              # color[4]
            out.sw32(pc, c + 4, 5)         # rotationDelta/Total, size[2], scale
            c += 24
    vis = _u32le(pc, eb + 196)
    if etype == TYPE_DECAL:
        if vis in PTRS:
            mb = c
            for i in range(vcount):        # FxElemMarkVisuals: 2 material ptrs each
                out.ptr(pc, mb + i * 8)
                out.ptr(pc, mb + i * 8 + 4)
            c = mb + vcount * 8
            for i in range(vcount):
                for k in (0, 4):
                    if _u32le(pc, mb + i * 8 + k) in PTRS:
                        c = _conv_material_inline(pc, c, out)
    elif vcount > 1:
        if vis in PTRS:
            ab = c
            for i in range(vcount):        # FxElemVisuals ptr array
                out.ptr(pc, ab + i * 4)
            c = ab + vcount * 4
            for i in range(vcount):
                c = _conv_visual_dyn(pc, c, _u32le(pc, ab + i * 4), etype, out)
    else:
        c = _conv_visual_dyn(pc, c, vis, etype, out)
    for off in (224, 228, 232):            # onImpact/onDeath/emitted fx-name refs
        if _u32le(pc, eb + off) in PTRS:
            c = out.cstr(pc, c)
    if _u32le(pc, eb + 252) in PTRS:       # effectAttached
        c = out.cstr(pc, c)
    if _u32le(pc, eb + 256) in PTRS:       # extended
        if etype == TYPE_TRAIL:
            tb = c
            out.sw32(pc, tb, 4)            # scrollTimeMsec/repeatDist/splitDist/vertCount
            out.ptr(pc, tb + 16)           # verts
            out.sw32(pc, tb + 20)          # indCount
            out.ptr(pc, tb + 24)           # inds
            c = tb + 28
            vc_, ic_ = _u32le(pc, tb + 12), _u32le(pc, tb + 20)
            if _u32le(pc, tb + 16) in PTRS:
                out.sw32(pc, c, vc_ * 5); c += vc_ * 20   # FxTrailVertex: 5 floats
            if _u32le(pc, tb + 24) in PTRS:
                for i in range(ic_):
                    out.sw16(pc, c + i * 2)
                c += ic_ * 2
        elif etype == TYPE_SPOT_LIGHT:
            out.sw32(pc, c, 3); c += 12    # FxSpotLightDef: 3 floats
        else:
            out.raw(pc, c, 1); c += 1      # unknownDef: single char
    if _u32le(pc, eb + 280) in PTRS:       # spawnSound
        c = out.cstr(pc, c)
    return c


def convert_fx(pc, off, reloc=_default_reloc):
    """Full PC FxEffectDef -> console. Returns (body_bytes, pc_end, ptr_offs)
    where ptr_offs are output offsets of relocated non-sentinel pointers (for
    oracle-diff masking)."""
    out = _Out(reloc)
    out.b += convert_fx_header(pc, off, reloc)
    if _u32le(pc, off) not in PTRS and _u32le(pc, off) != 0:
        out.ptr_offs.append(0)
    c = off + FX_HDR
    if _u32le(pc, off) in PTRS:
        c = out.cstr(pc, c)                # name string
    n = (struct.unpack_from('<h', pc, off + 8)[0] +
         struct.unpack_from('<h', pc, off + 10)[0] +
         struct.unpack_from('<h', pc, off + 12)[0])
    if _u32le(pc, off + 28) in PTRS:
        base = c
        for i in range(n):                 # all fixed 292-B bodies first
            _conv_elem_fixed(pc, base + i * ED, out)
        c = base + n * ED
        for i in range(n):                 # then per-elem dynamic tails
            c = _conv_elem_dyn(pc, base + i * ED, c, out)
    if _u32le(pc, off + 28) not in PTRS and _u32le(pc, off + 28) != 0:
        out.ptr_offs.append(28)
    return bytes(out.b), c, out.ptr_offs
