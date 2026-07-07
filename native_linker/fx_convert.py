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
