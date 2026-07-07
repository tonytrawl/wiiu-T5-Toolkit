#!/usr/bin/env python3
"""
Task #28: console (Wii U) GfxWorld layout probe for T6 (mp_raid_genuine.zone).

Anchors: GfxWorld body found at 0x2b7029d (asset 847), preceded by a byte-exact
techset end; next anchor is techset 849 at 0x40f5989 (GameWorldMp 848 between).

SOLVED BODY (console GfxWorld = 1076 bytes, PC-32 1016):
  +0..395  PC-identical (name..dpvsPlanes..cellBitsCount, cells, sunParse etc.)
  +396     GfxWorldDraw console = 116 bytes (PC 56): see CONSOLE_DRAW below
  +512     GfxLightGrid PC-identical (72)
  +584     tail PC-identical, shifted +60 (modelCount@584 ... lightingQuality@1072)

Walks the full dynamic stream with per-section validation.
"""
import struct
import sys

import struct_layout
import shader_probe

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)
IMG_SIZE = 328

L = struct_layout.Layout("../tools/ref_oat/src/Common/Game/T6/T6_Assets.h",
                         console=True)


def u32(d, o):
    return struct.unpack('>I', d[o:o+4])[0]


def u16(d, o):
    return struct.unpack('>H', d[o:o+2])[0]


class Cur:
    def __init__(self, d, o):
        self.d = d
        self.o = o
        self.log = []

    def mark(self, label):
        self.log.append((label, self.o))
        print('  %-42s cur=0x%08x' % (label, self.o))

    def skip(self, n):
        self.o += n

    def cstr(self, maxlen=160):
        e = self.d.index(b'\x00', self.o)
        s = self.d[self.o:e]
        self.o = e + 1
        return s.decode('latin-1', 'replace')


def consume_image(d, c):
    b = c.o
    c.skip(IMG_SIZE)
    if u32(d, b+320) in PTRS:
        c.cstr()
    if u32(d, b+176) in PTRS and d[b+171] == 0:
        c.skip(u32(d, b+160))


def sz(name):
    return L.get(name)['size']


def walk(d, b):
    g = lambda off: u32(d, b + off)
    c = Cur(d, b + 1076)
    c.mark('start (body end)')

    # -- streamInfo (embedded @20): aabbTrees, leafRefs
    atc, atp = g(20), g(24)
    lrc, lrp = g(28), g(32)
    if atp in PTRS:
        # GfxStreamingAabbTree = 48 PC-32; has no inner pointers
        c.skip(atc * sz('GfxStreamingAabbTree'))
        c.mark('streamInfo.aabbTrees x%d' % atc)
    if lrp in PTRS:
        c.skip(lrc * 4)
        c.mark('streamInfo.leafRefs x%d' % lrc)

    # -- sunLight (GfxLight, reusable)
    if g(256) in PTRS:
        c.skip(sz('GfxLight'))
        c.mark('sunLight (GfxLight %d)' % sz('GfxLight'))

    # -- volume arrays
    for cnt_o, ptr_o, tname, label in [
            (268, 272, 'GfxLightCorona', 'coronas'),
            (276, 280, 'GfxShadowMapVolume', 'shadowMapVolumes'),
            (284, 288, 'GfxVolumePlane', 'shadowMapVolumePlanes'),
            (292, 296, 'GfxExposureVolume', 'exposureVolumes'),
            (300, 304, 'GfxVolumePlane', 'exposureVolumePlanes'),
            (308, 312, 'GfxWorldFogVolume', 'worldFogVolumes'),
            (316, 320, 'GfxVolumePlane', 'worldFogVolumePlanes'),
            (324, 328, 'GfxWorldFogModifierVolume', 'worldFogModifierVolumes'),
            (332, 336, 'GfxVolumePlane', 'worldFogModifierVolumePlanes'),
            (340, 344, 'GfxLutVolume', 'lutVolumes'),
            (348, 352, 'GfxVolumePlane', 'lutVolumePlanes')]:
        if g(ptr_o) in PTRS and g(cnt_o):
            c.skip(g(cnt_o) * sz(tname))
            c.mark('%s x%d' % (label, g(cnt_o)))

    # -- dpvsPlanes (embedded @372): {cellCount, planes*, nodes*, sceneEntCellBits*}
    cellCount = g(372)
    if g(376) in PTRS:
        c.skip(g(8) * 20)              # planes: planeCount x cplane_s(20)
        c.mark('dpvsPlanes.planes x%d' % g(8))
    if g(380) in PTRS:
        c.skip(g(12) * 2)              # nodes: nodeCount x u16
        c.mark('dpvsPlanes.nodes x%d' % g(12))
    # sceneEntCellBits: RUNTIME -> 0 stream bytes

    # -- cells (cellCount x GfxCell 48) + per-cell aabbTree/portals/probes
    if g(392) in PTRS:
        cb = c.o
        c.skip(cellCount * 48)
        c.mark('cells x%d bodies' % cellCount)
        for i in range(cellCount):
            co = cb + i*48
            # GfxCell: mins12 maxs12 aabbTreeCount@24 aabbTree*@28
            #          portalCount@32 portals*@36 reflectionProbeCount@40 probes*@44
            atc_, atp_ = u32(d, co+24), u32(d, co+28)
            pc_, pp_ = u32(d, co+32), u32(d, co+36)
            rc_, rp_ = u32(d, co+40), u32(d, co+44)
            if atp_ in PTRS:
                ab = c.o
                c.skip(atc_ * 40)      # GfxAabbTree bodies
                for j in range(atc_):
                    ao = ab + j*40
                    # smodelIndexes* @32? count @28? -> use layout:
                    # GfxAabbTree: mins12 maxs12 childrenOffset@24 u16 childCount@26 u16
                    #   smodelIndexCount@28 u32? ... derive from PC layout
                    sic = u16(d, ao+28)
                    sip = u32(d, ao+32)
                    if sip in PTRS:
                        c.skip(sic * 2)
            if pp_ in PTRS:
                pb = c.o
                c.skip(pc_ * 92)       # GfxPortal bodies
                for j in range(pc_):
                    po = pb + j*92
                    vcnt = d[po+88]    # hmm: vertexCount position from layout
                    vp = u32(d, po+8)  # vertices*
                    if vp in PTRS:
                        c.skip(vcnt * 12)
            if rp_ in PTRS:
                c.skip(rc_)            # reflectionProbes: u8 indexes
        c.mark('cells dynamics done')

    # -- draw (console layout, base +396):
    #    +400 reflectionProbeCount, +404 reflectionProbes*, +408 probeTextures*(RUNTIME)
    #    +412 lightmapCount, +416 lightmaps*, +420/+424 lightmap textures (RUNTIME)
    #    +428 vertexCount, +432 vertexDataSize0, +440 vd0.data*
    #    +464 vertexDataSize1, +472 vd1.data*, +496 indexCount, +500 indices*
    rpc = g(400)
    if g(404) in PTRS:
        rb = c.o
        rp_sz = sz('GfxReflectionProbe')
        c.skip(rpc * rp_sz)
        c.mark('draw.reflectionProbes x%d (%d each)' % (rpc, rp_sz))
        for i in range(rpc):
            ro = rb + i*rp_sz
            # GfxReflectionProbe: origin12, image*@12, probeVolumes*@16, count...
            img = u32(d, ro+12)
            if img in PTRS:
                consume_image(d, c)
            pvc = u32(d, ro+20)
            if u32(d, ro+16) in PTRS:
                c.skip(pvc * sz('GfxProbeVolume') if 'GfxProbeVolume' in L.structs else 0)
        c.mark('draw.reflectionProbes dynamics')
    if g(416) in PTRS:
        lb = c.o
        c.skip(g(412) * 8)             # GfxLightmapArray {primary*, secondary*}
        c.mark('draw.lightmaps x%d' % g(412))
        for i in range(g(412)):
            for k in (0, 4):
                if u32(d, lb + i*8 + k) in PTRS:
                    consume_image(d, c)
                    c.mark('draw.lightmap image inline')
    if g(440) in PTRS:
        c.skip(g(432))                 # vd0.data
        c.mark('draw.vd0.data %d bytes' % g(432))
    if g(472) in PTRS:
        c.skip(g(464))                 # vd1.data
        c.mark('draw.vd1.data %d bytes' % g(464))
    if g(500) in PTRS:
        c.skip(g(496) * 2)             # indices
        c.mark('draw.indices x%d' % g(496))

    # -- lightGrid (base +512, PC-identical 72)
    lg = 512
    mins = [u16(d, b+lg+4+2*k) for k in range(3)]
    maxs = [u16(d, b+lg+10+2*k) for k in range(3)]
    rowAxis = g(lg+20)
    if g(lg+28) in PTRS:
        cnt = maxs[rowAxis] - mins[rowAxis] + 1
        c.skip(cnt * 2)
        c.mark('lightGrid.rowDataStart x%d' % cnt)
    if g(lg+36) in PTRS:
        c.skip(g(lg+32))
        c.mark('lightGrid.rawRowData %d' % g(lg+32))
    if g(lg+44) in PTRS:
        c.skip(g(lg+40) * 4)
        c.mark('lightGrid.entries x%d' % g(lg+40))
    if g(lg+52) in PTRS:
        c.skip(g(lg+48) * sz('GfxCompressedLightGridColors'))
        c.mark('lightGrid.colors x%d' % g(lg+48))
    if g(lg+60) in PTRS:
        c.skip(g(lg+56) * sz('GfxCompressedLightGridCoeffs'))
        c.mark('lightGrid.coeffs x%d (%d each)' % (g(lg+56), sz('GfxCompressedLightGridCoeffs')))
    if g(lg+68) in PTRS:
        c.skip(g(lg+64) * sz('GfxSkyGridVolume'))
        c.mark('lightGrid.skyGridVolumes x%d' % g(lg+64))

    # -- models
    if g(588) in PTRS:
        c.skip(g(584) * sz('GfxBrushModel'))
        c.mark('models x%d (%d each)' % (g(584), sz('GfxBrushModel')))

    # -- materialMemory (entries are material asset refs + int)
    if g(624) in PTRS:
        mb = c.o
        c.skip(g(620) * 8)
        c.mark('materialMemory x%d' % g(620))
        for i in range(g(620)):
            if u32(d, mb + i*8) in PTRS:
                raise RuntimeError('inline material in materialMemory')

    # -- sun (embedded @628 console): sunflare_t has 2 Material* asset refs at head?
    # markers only unless FOLLOW (would inline material)
    for off in (628, 632):
        if g(off) in PTRS:
            print('  ! sunflare material inline at +%d' % off)

    # -- outdoorImage (asset ref @788)
    if g(788) in PTRS:
        consume_image(d, c)
        c.mark('outdoorImage inline')
    # cellCasterBits/sceneDyn*/primaryLight*ShadowVis: RUNTIME -> 0 bytes

    # -- shadowGeom: primaryLightCount x GfxShadowGeometry(12) + subarrays
    plc = g(264)
    if g(824) in PTRS:
        sb = c.o
        c.skip(plc * 12)
        c.mark('shadowGeom x%d' % plc)
        for i in range(plc):
            so = sb + i*12
            surfC, smodC = u16(d, so), u16(d, so+2)
            if u32(d, so+4) in PTRS:
                c.skip(surfC * 2)      # sortedSurfIndex
            if u32(d, so+8) in PTRS:
                c.skip(smodC * 2)      # smodelIndex
        c.mark('shadowGeom dynamics')

    # -- lightRegion: primaryLightCount x GfxLightRegion(8) + hulls + axis
    if g(828) in PTRS:
        rb = c.o
        c.skip(plc * 8)
        c.mark('lightRegion x%d' % plc)
        for i in range(plc):
            ro = rb + i*8
            hc = u32(d, ro)
            if u32(d, ro+4) in PTRS:
                hb = c.o
                c.skip(hc * 80)        # GfxLightRegionHull
                for j in range(hc):
                    ho = hb + j*80
                    ac = u32(d, ho+72)
                    if u32(d, ho+76) in PTRS:
                        c.skip(ac * 20)  # GfxLightRegionAxis
        c.mark('lightRegion dynamics')

    # -- dpvs (embedded @832 console = PC 772+60), reorder:
    # smodelVisData(RT) surfaceVisData(RT) ... smodelCastsShadow, sortedSurfIndex,
    # smodelInsts, surfaces, smodelDrawInsts, surfaceMaterials(RT)
    dp = 832
    smodelCount = g(dp+0)
    staticSurfaceCount = g(dp+4)
    # PC GfxWorldDpvsStatic: {smodelCount, staticSurfaceCount, surfaceVisDataCount?,
    #   ...} - print first words for manual mapping
    print('  dpvs head words:', ' '.join('%08x' % g(dp+4*k) for k in range(29)))
    return c


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'mp_raid_genuine.zone'
    d = open(path, 'rb').read()
    b = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x2b7029d
    walk(d, b)


if __name__ == '__main__':
    main()
