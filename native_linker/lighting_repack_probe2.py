#!/usr/bin/env python3
"""
POLISH probe v4: (a) verify tangent hypothesis console = ror1(lo u16), rol1(hi u16) over all
vd0 verts; (b) classify vd1 elements swap2 vs verbatim vs neither, per group/surface.
"""
import struct
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfxworld_assemble as GA


def get(cfgname):
    m, d, cfg = GA.walk(cfgname)
    spans = GA._spans(m, cfg['body'] + cfg['bodysize'])
    out = {}
    for k, a, b in spans:
        out.setdefault(k, []).append((a, b))
    return out, d


def ror1(x):
    return ((x >> 1) | (x << 15)) & 0xFFFF


def rol1(x):
    return ((x << 1) | (x >> 15)) & 0xFFFF


def main():
    ps, pc = get('pc')
    ws, wu = get('wiiu')
    (p_vd0a, _), (p_vd1a, p_vd1b) = ps['draw.vd.data']
    (w_vd0a, _), (w_vd1a, _) = ws['draw.vd.data']
    p_ia, p_ib = ps['draw.indices'][0]
    p_sa, p_sb = ps['dpvs.surfaces'][0]
    nsurf = (p_sb - p_sa) // 80
    nidx = (p_ib - p_ia) // 2
    idx = struct.unpack_from('<%dH' % nidx, pc, p_ia)
    VD1_SIZE = p_vd1b - p_vd1a

    surfs = []          # (off0, off1, vc, lightmapIndex, flags)
    g0, g1 = {}, {}
    for i in range(nsurf):
        po = p_sa + i * 80
        off0 = struct.unpack_from('<I', pc, po + 12)[0]
        off1 = struct.unpack_from('<I', pc, po + 28)[0]
        tri = struct.unpack_from('<H', pc, po + 42)[0]
        bidx = struct.unpack_from('<I', pc, po + 44)[0]
        lmap, rprobe, plight, flags = pc[po + 52], pc[po + 53], pc[po + 54], pc[po + 55]
        if tri and bidx + tri * 3 <= nidx:
            vc = max(idx[bidx:bidx + tri * 3]) + 1
            surfs.append((off0, off1, vc, lmap, flags))
            if off0 not in g0 or vc > g0[off0]:
                g0[off0] = vc
            if off1 not in g1 or vc > g1[off1]:
                g1[off1] = vc

    # (a) tangent hypothesis over ALL vd0 verts
    ok = bad = 0
    bad_samples = []
    for off, vc in sorted(g0.items()):
        p0, w0 = p_vd0a + off, w_vd0a + off
        for v in range(vc):
            b = p0 + v * 36 + 32
            c = w0 + v * 36 + 32
            lo, hi = struct.unpack_from('<HH', pc, b)
            clo, chi = struct.unpack_from('>HH', wu, c)
            if clo == ror1(lo) and chi == rol1(hi):
                ok += 1
            else:
                bad += 1
                if len(bad_samples) < 20:
                    bad_samples.append((lo, hi, clo, chi))
    print('TANGENT ror1/rol1: ok=%d bad=%d (%.4f%% exact)' % (ok, bad, 100.0 * ok / (ok + bad)))
    for lo, hi, clo, chi in bad_samples:
        print('  pc=(%04x,%04x) wu=(%04x,%04x) ror=%04x rol=%04x' %
              (lo, hi, clo, chi, ror1(lo), rol1(hi)))

    # (b) vd1 classification per element
    cnt = Counter()
    grp_class = {}
    for off, vc in sorted(g1.items()):
        if off + vc * 4 > VD1_SIZE:
            continue
        gc = Counter()
        for v in range(vc):
            p = pc[p_vd1a + off + v * 4: p_vd1a + off + v * 4 + 4]
            w = wu[w_vd1a + off + v * 4: w_vd1a + off + v * 4 + 4]
            sw = p[0:2][::-1] + p[2:4][::-1]
            both_lo = p[0] == p[1]
            if w == sw and w == p:
                gc['ambig'] += 1
            elif w == sw:
                gc['swap2'] += 1
            elif w == p:
                gc['verbatim'] += 1
            else:
                # try swap4 and half-swaps
                if w == p[::-1]:
                    gc['swap4'] += 1
                elif w[0:2] == sw[0:2] and w[2:4] == p[2:4]:
                    gc['lo-swap-only'] += 1
                elif w[0:2] == p[0:2] and w[2:4] == sw[2:4]:
                    gc['hi-swap-only'] += 1
                else:
                    gc['neither'] += 1
        cnt.update(gc)
        # classify group
        key = tuple(sorted(k for k in gc if k != 'ambig'))
        grp_class.setdefault(key, []).append((off, vc, dict(gc)))
    print('vd1 element classes:', dict(cnt))
    print('vd1 group classes:')
    for key, lst in sorted(grp_class.items(), key=lambda kv: -len(kv[1])):
        print('  %-40s groups=%d  e.g. %s' % (key, len(lst), lst[0]))

    # correlate mismatch groups with surface lightmapIndex/flags
    mixed = {off for key, lst in grp_class.items() if key and 'swap2' not in key or True
             for off, vc, gc in lst if gc.get('verbatim') or gc.get('neither')}
    fl = Counter()
    for off0, off1, vc, lmap, flags in surfs:
        tag = 'mismatchgrp' if off1 in mixed else 'cleangrp'
        fl['%s lmap=%d flags=0x%02x' % (tag, lmap, flags)] += 1
    for k, v in sorted(fl.items()):
        print('  %-36s %d' % (k, v))


if __name__ == '__main__':
    main()
