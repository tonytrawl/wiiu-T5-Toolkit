#!/usr/bin/env python3
"""
Full GfxWorldDpvsStatic + trailing GfxWorld walker (console/Wii U, big-endian).

Continues from gfxworld_probe.walk() (which stops at the dpvs array start) and
models the write path (gfxworld_t6_write_db.cpp) exactly:

dpvs static (body @832, 116 bytes) file-emitted arrays IN ORDER:
  - smodelVisData[0..2], surfaceVisData[0..2], smodelVisDataCameraSaved,
    surfaceVisDataCameraSaved, surfaceCastsSunShadow, surfaceCastsShadow:
    ALL wrapped in XFILE_BLOCK_RUNTIME_VIRTUAL -> ZERO file bytes.
  - smodelCastsShadow: align128, smodelVisDataCount bytes   (NOT runtime)
  - sortedSurfIndex:   align2,  staticSurfaceCount * u16
  - smodelInsts:       align4,  smodelCount * 36
  - surfaces:          align16, GfxWorld.surfaceCount * 80  (material ref @48)
  - smodelDrawInsts:   align4,  smodelCount * 208 (console); per-inst:
        model asset ref @32; lmapVertexInfo[4] embedded @80 stride 32:
        colors ptr @+0 -> align4, numLmapVertexColors(@+24) * u32
  - surfaceMaterials: RUNTIME -> 0 bytes
dpvsDyn (@948): everything RUNTIME -> 0 bytes
waterBuffers[2] embedded @1004 stride 8 {bufferSize@0, buffer@4}:
    buffer -> align4, (bufferSize/16)*16 bytes
water/corona/rope/lut materials @1020/1024/1028/1032: asset refs (no bytes
    expected; abort if FOLLOW marker seen)
occluders:     @1040 ptr, count @1036, 68 each, align4
outdoorBounds: @1048 ptr, count @1044, 24 each, align4
heroLights:    @1060 ptr, count @1052, 56 each, align4
heroLightTree: @1064 ptr, count @1056, 32 each, align4
console siege-skin shader tail: 11085 verbatim bytes

Alignment is in virtual-block space; file offset differs by a constant delta.
We fit delta (mod 128) so the GENUINE walk lands exactly on the target end.

Usage:  python dpvs_walk_full.py <zone> <gfxworld_body> <target_end|-> [delta]
  genuine: python dpvs_walk_full.py mp_raid_genuine.zone 0x2b7029d 0x40aa61d
  ours:    python dpvs_walk_full.py ../mp_raid_rewrite.ff 0x3fcdd15 <our_gwmp> <delta>
If target is '-' the walk just reports where it lands. If delta is omitted,
all 128 deltas are tried and those hitting the target are reported.
"""
import struct
import sys

import gfxworld_probe as GP
import walker as WK

PTRS = GP.PTRS
SIEGE_TAIL = 11085

_MATWALK = None


def matwalker(d):
    global _MATWALK
    if _MATWALK is None:
        _MATWALK = WK.Walker(d, GP.L, WK.ZoneCode(WK.ZC_DIR))
    return _MATWALK


def u32(d, o):
    return struct.unpack('>I', d[o:o+4])[0]


class Walk:
    def __init__(self, d, o, delta, verbose=True):
        self.d = d
        self.o = o
        self.delta = delta
        self.verbose = verbose
        self.trace = []

    def align(self, a):
        r = (self.o + self.delta) % a
        if r:
            self.o += a - r

    def skip(self, n, label):
        self.trace.append((label, self.o, n))
        if self.verbose:
            print('  %-46s @0x%08x +%d' % (label, self.o, n))
        self.o += n


def walk_tail(d, b, start, delta, verbose=True):
    """Walk from dpvs-array start to GfxWorld end. Returns Walk."""
    g = lambda off: u32(d, b + off)
    w = Walk(d, start, delta, verbose)
    dp = 832
    smodelCount = g(dp+0)
    ssc = g(dp+4)
    smvc = g(dp+40)
    surfaceCount = g(16)
    p = lambda off: g(dp+off) in PTRS

    # ---- dpvs static ----
    if p(108):
        w.align(128)
        w.skip(smvc, 'dpvs.smodelCastsShadow x%d' % smvc)
    if p(80):
        w.align(2)
        w.skip(ssc*2, 'dpvs.sortedSurfIndex x%d' % ssc)
    if p(84):
        w.align(4)
        w.skip(smodelCount*36, 'dpvs.smodelInsts x%d (36)' % smodelCount)
    if p(88):
        w.align(16)
        sb = w.o
        w.skip(surfaceCount*80, 'dpvs.surfaces x%d (80)' % surfaceCount)
        for i in range(surfaceCount):
            if u32(d, sb + i*80 + 48) in PTRS:
                raise RuntimeError('INLINE material at surface %d (0x%x)'
                                   % (i, sb + i*80 + 48))
    if p(92):
        ib = None
        w.align(4)
        ib = w.o
        w.skip(smodelCount*208, 'dpvs.smodelDrawInsts x%d (208)' % smodelCount)
        n_lmap = 0
        for i in range(smodelCount):
            io = ib + i*208
            if u32(d, io+32) in PTRS:
                raise RuntimeError('INLINE xmodel at drawInst %d (0x%x)'
                                   % (i, io+32))
            for k in range(4):
                lo = io + 80 + k*32
                if u32(d, lo) in PTRS:
                    cnt = u32(d, lo+24)
                    w.align(4)
                    w.skip(cnt*4, 'drawInst[%d].lmapVertexInfo[%d] x%d'
                           % (i, k, cnt))
                    n_lmap += 1
        if verbose:
            print('  (lmapVertexColors arrays: %d)' % n_lmap)
    # surfaceMaterials, dpvsDyn: RUNTIME -> 0 bytes

    # ---- waterBuffers[2] embedded @1004 ----
    for i in range(2):
        wb = 1004 + i*8
        if g(wb+4) in PTRS:
            bs = g(wb)
            w.align(4)
            w.skip((bs//16)*16, 'waterBuffers[%d] %d bytes' % (i, bs))

    # ---- material refs (may be inline: TEMP block, align 4, full Material) ----
    for off, nm in ((1020, 'waterMaterial'), (1024, 'coronaMaterial'),
                    (1028, 'ropeMaterial'), (1032, 'lutMaterial')):
        if g(off) in PTRS:
            w.align(4)
            mb = w.o
            w.o = matwalker(d).walk('Material', w.o)
            w.trace.append(('inline %s Material' % nm, mb, w.o - mb))
            if verbose:
                print('  %-46s @0x%08x +%d' % ('inline %s Material' % nm,
                                               mb, w.o - mb))

    # ---- trailing arrays ----
    for cnt_o, ptr_o, esz, nm in ((1036, 1040, 68, 'occluders'),
                                  (1044, 1048, 24, 'outdoorBounds'),
                                  (1052, 1060, 56, 'heroLights'),
                                  (1056, 1064, 32, 'heroLightTree')):
        if g(ptr_o) in PTRS:
            w.align(4)
            w.skip(g(cnt_o)*esz, '%s x%d (%d)' % (nm, g(cnt_o), esz))

    # ---- console siege-skin shader tail ----
    w.skip(SIEGE_TAIL, 'siege-skin shader tail')
    return w


def main():
    path, body = sys.argv[1], int(sys.argv[2], 0)
    target = None if sys.argv[3] == '-' else int(sys.argv[3], 0)
    d = open(path, 'rb').read()

    # run the section walker up to the dpvs array start (quiet-ish)
    print('== section walk (gfxworld_probe) ==')
    c = GP.walk(d, body)
    start = c.o
    print('== dpvs arrays start: 0x%08x ==' % start)

    if len(sys.argv) > 4:
        deltas = [int(sys.argv[4], 0)]
    elif target is None:
        deltas = [0]
    else:
        # fit: quiet pass over all deltas
        hits = []
        for dl in range(128):
            try:
                w = walk_tail(d, body, start, dl, verbose=False)
                if w.o == target:
                    hits.append(dl)
            except RuntimeError:
                pass
        print('deltas hitting target 0x%08x: %s' % (target, hits))
        if not hits:
            # report landing spread for diagnosis
            for dl in range(0, 128, 16):
                try:
                    w = walk_tail(d, body, start, dl, verbose=False)
                    print('  delta=%3d -> end=0x%08x (miss %+d)'
                          % (dl, w.o, w.o - target))
                except RuntimeError as e:
                    print('  delta=%3d -> ERROR %s' % (dl, e))
            sys.exit(1)
        deltas = hits[:1]

    dl = deltas[0]
    print('== full tail walk, delta=%d ==' % dl)
    w = walk_tail(d, body, start, dl, verbose=True)
    print('END = 0x%08x' % w.o)
    if target is not None:
        print('TARGET 0x%08x  %s (diff %+d)'
              % (target, 'EXACT MATCH' if w.o == target else 'MISS',
                 w.o - target))


if __name__ == '__main__':
    main()
