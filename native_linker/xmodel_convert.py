#!/usr/bin/env python3
"""
XModel PC(v147, LE) -> console(WiiU v148, BE) converter  (HANDOFF Track C).

This module converts the XModel *body* (the 248 B PC struct -> 244 B console struct), its
non-surface trailing data, AND the XSurface block (convert_xmodel_surfaces, below).

XSurface (80 -> 128 B) validated vs genuine mp_raid/zm_transit (validate_xmodel_surface.py):
headers byte-exact (masked omap ptrs), per-surface dynamic (verts0/verts1/vertList/triIndices)
byte-exact EXCEPT two inherently-non-reproducible regions, and 100% self-resync on 260 MP + 35 ZM
models. The two lossy regions (documented, not bugs): (1) verts0 normal/tangent (PC's 10-bit
packed frame already lost precision, see latte_vertex); (2) collision-tree node counts (the console
linker REBUILDS the surface BVH — nc 18 vs PC 20 seen; leaves match). Weapon *_view models diverge
wholesale (console re-authored the mesh, different vert/tri counts) — same caveat as the body.

== Body layout (verified vs genuine common_mp, 465 matched pairs) ==
Console XModel = 244 B, PC = 248 B. PC-identical through offset +208; PC's `bool bad`@212 (+3 pad)
is DROPPED and the tail shifts -4. Every field is a plain byte-swap / pointer-relocate EXCEPT:
  * himipInvSqRadii (ptr @200): PC = null, console = FOLLOW to an inline `numsurfs` f32 array that
    the console linker GENERATES (per-surface inverse-square himip radius). NOT derivable from PC
    by copy — must be synthesized (passed in via `himip`).
  * memUsage (@204): a console-computed memory-usage stat; differs from PC. Passed in via `memusage`.
Both are the only non-PC-derivable body fields; everything else is byte-exact from PC.

Pointer fields (name, boneNames, parentList, quats, trans, partClassification, baseMat, surfs,
materialHandles, collSurfs, boneInfo, physPreset, collmaps, physConstraints) are remapped through
`reloc` (default identity for tests; wire to the omap at integration).
"""
import struct

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)
PC_BODY = 248
CO_BODY = 244


def _default_reloc(v):
    return v


def _sw32(pc, o):
    return struct.pack('>I', struct.unpack_from('<I', pc, o)[0])

def _sw16(pc, o):
    return struct.pack('>H', struct.unpack_from('<H', pc, o)[0])


def _lodinfo(pc, o):
    """One XModelLodInfo (28 B, same size both platforms)."""
    b = bytearray()
    b += _sw32(pc, o + 0)                 # dist (f32)
    b += _sw16(pc, o + 4)                 # numsurfs (u16)
    b += _sw16(pc, o + 6)                 # surfIndex (u16)
    for k in range(5):
        b += _sw32(pc, o + 8 + k * 4)     # partBits[5]
    return bytes(b)


def convert_xmodel_bonedata(pc, body_off):
    """Convert the contiguous trailing bone-data block that follows the XModel body and precedes
    the surfaces: name string, boneNames, parentList, quats, trans, partClassification, baseMat.
    Sub-structs are the same size on both platforms; per-array swap/verbatim verified vs genuine
    common_mp (363-swap boneNames, etc). Returns (console_bytes, next_pc_off) where next_pc_off
    points at the `surfs` array (surface conversion is a separate sub-project).
    boneInfo/collSurfs/himip/physPreset/collmaps come AFTER surfaces and are not handled here."""
    nb, nrb = pc[body_off + 4], pc[body_off + 5]
    n = nb - nrb
    out = bytearray()
    src = body_off + PC_BODY
    def p(o):
        return struct.unpack_from('<I', pc, body_off + o)[0]

    if p(0) in PTRS:                                   # name c-string
        end = pc.index(0, src); out += pc[src:end + 1]; src = end + 1
    if p(8) in PTRS:                                   # boneNames: nb x ScriptString(u16) — swap
        for i in range(nb):
            out += _sw16(pc, src + i * 2)
        src += 2 * nb
    if p(12) in PTRS:                                  # parentList: (nb-nrb) x u8 — verbatim
        out += pc[src:src + n]; src += n
    if p(16) in PTRS:                                  # quats: (nb-nrb) x XModelQuat(4 s16) — swap
        for i in range(n * 4):
            out += _sw16(pc, src + i * 2)
        src += 8 * n
    if p(20) in PTRS:                                  # trans: (nb-nrb) x 4 f32 — swap
        for i in range(n * 4):
            out += _sw32(pc, src + i * 4)
        src += 16 * n
    if p(24) in PTRS:                                  # partClassification: nb x u8 — verbatim
        out += pc[src:src + nb]; src += nb
    if p(28) in PTRS:                                  # baseMat: nb x DObjAnimMat(8 f32) — swap
        for i in range(nb * 8):
            out += _sw32(pc, src + i * 4)
        src += 32 * nb
    return bytes(out), src


# ------------------------------------------------------------------ surfaces
# PC XSurface = 80 B, console = 128 B (a GX2 struct, NOT a shifted PC struct).
# Header field map (derived empirically vs genuine common_mp/mp_raid, aligned by
# model-name + surface-index; see /tmp/align_surf.py exploration):
#   off  PC(80,LE)                     console(128,BE)
#   +0   tileMode u8                   +0   (copy)
#   +1   vertListCount u8              +1   (copy)
#   +2   flags u16                     +2   (swap)
#   +4   vertCount u16                 +4   (swap)
#   +6   triCount u16                  +6   (swap)
#   +8   baseTriIndex u16              +8   (swap)
#   +10  baseVertIndex u16             +10  (swap)
#   +12  triIndices*                   +12  (ptr)
#   +16  vertInfo.vertCount[4] i16     +16  (4x swap)
#   +24  vertsBlend* (skinned)         +24  (skinned; raise for now)
#   +28  tensionData* (skinned)        +28
#   +32  verts0*                       +52  (ptr)  <-- RELOCATED slot
#   --                                 +72  verts1* (NEW console 2nd stream; FOLLOW)
#   +40  vertList*                     +96  (ptr)  <-- RELOCATED slot
#   +48  partBits[5] u32               +108 (5x swap)
# verts0/verts1/triIndices are LINEAR buffers (no GX2 tiling); latte_vertex
# re-encodes them byte-exact contiguously.  Console per-surface dynamic order:
# verts0 (24*vc) -> verts1 (8*vc) -> vertList(+trees) -> triIndices (6*tc).
SURF_PC = 80
SURF_CO = 128


def _u16le(d, o):
    return struct.unpack_from('<H', d, o)[0]

def _u32le(d, o):
    return struct.unpack_from('<I', d, o)[0]


def _ptr(v, reloc):
    """Pointer word -> BE console word: FOLLOW/INSERT preserved, else relocated."""
    return struct.pack('>I', v if v in PTRS else reloc(v))


def convert_surface_header(pc, o, reloc=_default_reloc):
    """One PC XSurface header (80 B) -> console header (128 B)."""
    if _u32le(pc, o + 24) in PTRS or _u32le(pc, o + 28) in PTRS:
        raise NotImplementedError('skinned surface header (flags&2): needs Latte GX2 skin-stream '
                                  'synthesis (vertsBlend swaps, tension->skin-streams does not)')
    out = bytearray(SURF_CO)
    out[0] = pc[o + 0]                                     # tileMode
    out[1] = pc[o + 1]                                     # vertListCount
    struct.pack_into('>H', out, 2, _u16le(pc, o + 2))     # flags
    struct.pack_into('>H', out, 4, _u16le(pc, o + 4))     # vertCount
    struct.pack_into('>H', out, 6, _u16le(pc, o + 6))     # triCount
    struct.pack_into('>H', out, 8, _u16le(pc, o + 8))     # baseTriIndex
    struct.pack_into('>H', out, 10, _u16le(pc, o + 10))   # baseVertIndex
    out[12:16] = _ptr(_u32le(pc, o + 12), reloc)          # triIndices
    for j in range(4):                                    # vertInfo.vertCount[4]
        out[16 + j * 2:18 + j * 2] = _sw16(pc, o + 16 + j * 2)
    out[52:56] = _ptr(_u32le(pc, o + 32), reloc)          # verts0  (PC@32 -> CO@52)
    v0 = _u32le(pc, o + 32)
    out[72:76] = struct.pack('>I', FOLLOW) if v0 in PTRS else b'\0\0\0\0'  # verts1 (synth)
    out[96:100] = _ptr(_u32le(pc, o + 40), reloc)         # vertList (PC@40 -> CO@96)
    for j in range(5):                                    # partBits[5] (PC@48 -> CO@108)
        out[108 + j * 4:112 + j * 4] = _sw32(pc, o + 48 + j * 4)
    return bytes(out)


def _convert_vertlist(pc, c, vlc, reloc):
    """PC vertList (vlc x XRigidVertList(12) + optional XSurfaceCollisionTree) -> console."""
    out = bytearray()
    base = c[0]
    c[0] += vlc * 12
    for k in range(vlc):
        vl = base + k * 12
        for j in range(4):                        # boneOffset/vertCount/triOffset/triCount u16
            out += _sw16(pc, vl + j * 2)
        out += _ptr(_u32le(pc, vl + 8), reloc)    # collisionTree*
    for k in range(vlc):
        vl = base + k * 12
        if _u32le(pc, vl + 8) not in PTRS:
            continue
        tb = c[0]
        c[0] += 40
        for j in range(6):                        # trans[3]+scale[3] f32
            out += _sw32(pc, tb + j * 4)
        out += _sw32(pc, tb + 24)                 # nodeCount
        out += _ptr(_u32le(pc, tb + 28), reloc)   # nodes*
        out += _sw32(pc, tb + 32)                 # leafCount
        out += _ptr(_u32le(pc, tb + 36), reloc)   # leafs*
        nc = _u32le(pc, tb + 24)
        lc = _u32le(pc, tb + 32)
        if _u32le(pc, tb + 28) in PTRS:
            nb = c[0]; c[0] += nc * 16
            for i in range(nc * 8):               # XSurfaceCollisionNode = 8 u16
                out += _sw16(pc, nb + i * 2)
        if _u32le(pc, tb + 36) in PTRS:
            lb = c[0]; c[0] += lc * 2
            for i in range(lc):                   # XSurfaceCollisionLeaf = 1 u16
                out += _sw16(pc, lb + i * 2)
    return bytes(out)


def convert_xmodel_surfaces(pc, sb, ns, reloc=_default_reloc):
    """Convert the surfs[ns] header block + all per-surface dynamic data.
    `sb` = PC surfs-array offset. Returns (console_bytes, next_pc_off).
    Console layout: ns x 128-B header, then per surface: verts0(24*vc) verts1(8*vc)
    vertList(+trees) triIndices(6*tc)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
    from latte_vertex import pc_vertex_to_console
    out = bytearray()
    for i in range(ns):
        out += convert_surface_header(pc, sb + i * SURF_PC, reloc)
    c = [sb + ns * SURF_PC]
    for i in range(ns):
        o = sb + i * SURF_PC
        flags = _u16le(pc, o + 2)
        vc = _u16le(pc, o + 4)
        tc = _u16le(pc, o + 6)
        vlc = pc[o + 1]
        if _u32le(pc, o + 24) in PTRS or _u32le(pc, o + 28) in PTRS:
            # skinned pre-verts0 blob: vertsBlend IS a clean u16 byte-swap (PC c001->console 01c0,
            # same 0x01c0 values, size vb = (vc0+3vc1+5vc2+7vc3)*2, identical both sides). BUT PC's
            # tensionData (sum(vc)*4 f32) does NOT map: the console replaces it with Latte GX2 skin
            # streams (size 2*lo16(s28)+2*hi16(s28)+2*s40, scalars @28/@40 — e.g. 16836 B vs PC's
            # 8492 B tension for viewmodel_hands_cloth). Those hardware skin streams must be
            # SYNTHESISED (GX2 skinning-vertex RE), not swapped — the real remaining blocker.
            raise NotImplementedError('skinned surface (flags&2): vertsBlend swaps but console Latte '
                                      'GX2 skin streams need synthesis — see convert_xmodel_surfaces')
        if not (flags & 1) and _u32le(pc, o + 32) in PTRS:
            vsrc = c[0]
            c[0] += vc * 32
            v0blk = bytearray(); v1blk = bytearray()
            for v in range(vc):
                a, b = pc_vertex_to_console(pc, vsrc + v * 32)
                v0blk += a; v1blk += b
            out += v0blk; out += v1blk
        if _u32le(pc, o + 40) in PTRS:
            out += _convert_vertlist(pc, c, vlc, reloc)
        if _u32le(pc, o + 12) in PTRS:
            tsrc = c[0]
            c[0] += tc * 6
            for t in range(tc * 3):
                out += _sw16(pc, tsrc + t * 2)
    return bytes(out), c[0]


def convert_xmodel_materialhandles(pc, base, ns, reloc=_default_reloc):
    """materialHandles: ns pointer words (relocated); FOLLOW -> inline console Material
    (via material_convert.convert_material). Returns (console_bytes, next_pc_off)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import material_convert as MC
    out = bytearray()
    for i in range(ns):
        out += _ptr(_u32le(pc, base + i * 4), reloc)
    c = base + ns * 4
    for i in range(ns):
        if _u32le(pc, base + i * 4) in PTRS:
            mb, c = MC.convert_material(pc, c, reloc)
            out += mb
    return bytes(out), c


# ------------------------------------------------------ post-surface tail
# Stream order after materialHandles: collSurfs -> boneInfo -> himipInvSqRadii -> physPreset
# (-> collmaps -> physConstraints, handled in the full driver).
# collSurfs: PC XModelCollSurf_s = 44 (+ inline collTris[numCollTris] x 48) -> console = 36 and
#   the collTris are DROPPED.  Field map (empirically pinned vs genuine common_mp):
#     PC44 = { collTris* @0, numCollTris @4, Bounds bounds @8 (mins3+maxs3 f32, 24 B),
#              int @32, int @36, int @40 }.
#   console36 = PC[+8 .. +43] byte-swapped as 9 words (bounds + the 3 trailing ints); the LEADING
#   {collTris*, numCollTris} pair is removed (console reads collTris out-of-line / not at all).
COLLSURF_PC = 44
COLLSURF_CO = 36
COLLTRI = 48
XBONEINFO = 44
PHYSPRESET = 84


def convert_xmodel_collsurfs(pc, base, ncoll, reloc=_default_reloc):
    """PC collSurfs (44 B each + collTris) -> console collSurfs (36 B each, collTris dropped)."""
    out = bytearray()
    c = base + COLLSURF_PC * ncoll
    for i in range(ncoll):
        cs = base + i * COLLSURF_PC
        # console36 = PC[+8..+43] swapped as 9 words (bounds f32 x6 + 3 ints); the leading
        # {collTris* @0, numCollTris @4} pair is dropped.
        for w in range(9):
            out += _sw32(pc, cs + 8 + w * 4)
    for i in range(ncoll):
        cs = base + i * COLLSURF_PC
        if _u32le(pc, cs + 0) in PTRS:                  # collTris* present -> consume+drop
            c += _u32le(pc, cs + 4) * COLLTRI
    return bytes(out), c


def convert_xmodel_boneinfo(pc, base, nb):
    """boneInfo: nb x XBoneInfo(44). Same size both platforms; byte-swap the 11 words each."""
    out = bytearray()
    for i in range(nb):
        for w in range(11):
            out += _sw32(pc, base + i * XBONEINFO + w * 4)
    return bytes(out), base + XBONEINFO * nb


def convert_xmodel_physpreset(pc, base, reloc=_default_reloc):
    """physPreset: inline PhysPreset(84) + name + sndAliasPrefix strings.
    Field-swap the 21 words; name(@0)/sndAlias(@28) pointers relocated, strings copied."""
    out = bytearray()
    for w in range(PHYSPRESET // 4):
        o = base + w * 4
        if w * 4 in (0, 28):
            out += _ptr(_u32le(pc, o), reloc)
        else:
            out += _sw32(pc, o)
    c = base + PHYSPRESET
    for so in (0, 28):
        if _u32le(pc, base + so) in PTRS:
            end = pc.index(0, c)
            out += pc[c:end + 1]
            c = end + 1
    return bytes(out), c


def convert_xmodel_body(pc, off, reloc=_default_reloc, memusage=None, himip=FOLLOW):
    """PC XModel body @off -> console 244 B body. `memusage` (u32) and `himip` (ptr word) are the
    two non-PC-derivable fields; default himip=FOLLOW (console generates the inline array)."""
    def ptr(o):
        return struct.pack('>I', reloc(struct.unpack_from('<I', pc, o)[0]))
    out = bytearray()
    out += ptr(off + 0)                    # name
    out += pc[off + 4: off + 8]            # numBones, numRootBones, numsurfs, lodRampType
    for o in (8, 12, 16, 20, 24, 28, 32, 36):
        out += ptr(off + o)                # 8 pointer members
    for i in range(4):
        out += _lodinfo(pc, off + 40 + i * 28)      # lodInfo[4] @40..151
    out += ptr(off + 152)                  # collSurfs
    out += _sw32(pc, off + 156)            # numCollSurfs
    out += _sw32(pc, off + 160)            # contents
    out += ptr(off + 164)                  # boneInfo
    out += _sw32(pc, off + 168)            # radius
    for k in range(3):
        out += _sw32(pc, off + 172 + k * 4)   # mins vec3
    for k in range(3):
        out += _sw32(pc, off + 184 + k * 4)   # maxs vec3
    out += _sw16(pc, off + 196)            # numLods
    out += _sw16(pc, off + 198)            # collLod
    out += struct.pack('>I', himip)        # himipInvSqRadii (console-generated; default FOLLOW)
    mu = struct.unpack_from('<I', pc, off + 204)[0] if memusage is None else memusage
    out += struct.pack('>I', mu)           # memUsage (console-computed; caller supplies)
    out += _sw32(pc, off + 208)            # flags
    # PC `bool bad` @212 (+3 pad) dropped; tail shifts -4
    out += ptr(off + 216)                  # physPreset
    out += pc[off + 220: off + 221]        # numCollmaps u8
    out += b'\x00' * 3                      # pad
    out += ptr(off + 224)                  # collmaps
    out += ptr(off + 228)                  # physConstraints
    # lightingOriginOffset vec3 + lightingOriginRange: copied VERBATIM (NOT byte-swapped) —
    # a linker quirk, 465/0 across the matched-pair oracle (cf. Material `contents`).
    out += pc[off + 232: off + 248]
    assert len(out) == CO_BODY, len(out)
    return bytes(out)


def convert_xmodel(pc, off, reloc=_default_reloc, memusage=None):
    """Full XModel PC->console driver: body -> bonedata -> surfaces -> materialHandles ->
    collSurfs -> boneInfo -> himipInvSqRadii -> physPreset -> (collmaps/physConstraints raise).
    Returns (console_bytes, next_pc_off).  Skinned surfaces raise NotImplementedError.

    Lossy/derived regions (self-consistent but not byte-identical to genuine, documented per
    section): verts0 normal/tangent, collision-tree node counts, boneInfo per-bone recomputed
    bounds, and inline-material image pixels (image-conversion track).  himipInvSqRadii is a
    console-generated numsurfs*f32 array (emitted; values synthesised as 0.0 when PC has none)."""
    nb, nrb, ns = pc[off + 4], pc[off + 5], pc[off + 6]
    ncoll = _u32le(pc, off + 156)
    body = convert_xmodel_body(pc, off, reloc, memusage=memusage, himip=FOLLOW)
    bones, cur = convert_xmodel_bonedata(pc, off)
    out = bytearray(body)
    out += bones
    # surfaces
    if _u32le(pc, off + 32) in PTRS:
        surf, cur = convert_xmodel_surfaces(pc, cur, ns, reloc)
        out += surf
    # materialHandles
    if _u32le(pc, off + 36) in PTRS:
        mh, cur = convert_xmodel_materialhandles(pc, cur, ns, reloc)
        out += mh
    # collSurfs
    if _u32le(pc, off + 152) in PTRS:
        cs, cur = convert_xmodel_collsurfs(pc, cur, ncoll, reloc)
        out += cs
    # boneInfo
    if _u32le(pc, off + 164) in PTRS:
        bi, cur = convert_xmodel_boneinfo(pc, cur, nb)
        out += bi
    # himipInvSqRadii: console-generated numsurfs f32 (body ptr forced FOLLOW above)
    if _u32le(pc, off + 200) in PTRS:
        cur += 4 * ns                              # consume PC copy if present
        out += b'\x00\x00\x00\x00' * ns            # synthesise (LOD himip radii)
    else:
        out += b'\x00\x00\x00\x00' * ns
    # physPreset
    if _u32le(pc, off + 216) in PTRS:
        pp, cur = convert_xmodel_physpreset(pc, cur, reloc)
        out += pp
    if _u32le(pc, off + 224) in PTRS and pc[off + 220]:
        raise NotImplementedError('collmaps conversion not built')
    if _u32le(pc, off + 228) in PTRS:
        raise NotImplementedError('inline physConstraints not built')
    return bytes(out), cur
