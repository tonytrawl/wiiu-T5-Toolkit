#!/usr/bin/env python3
"""
POLISH probe v3: per-field diff of GfxWorld vd0/vd1 vertex streams PC vs genuine WiiU (mp_raid).
Spans come from the validated gfxworld_assemble.walk/_spans pairing (mark offset = region END).
Groups per-surface from the index range (baseIndex@44, triCount@42, vc = max idx+1).
"""
import struct
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfxworld_assemble as GA


def get_spans(cfgname):
    m, d, cfg = GA.walk(cfgname)
    spans = GA._spans(m, cfg['body'] + cfg['bodysize'])
    out = {}
    for k, a, b in spans:
        out.setdefault(k, []).append((a, b))
    return out, d


def main():
    ps, pc = get_spans('pc')
    ws, wu = get_spans('wiiu')
    for k in ('draw.vd.data', 'draw.indices', 'dpvs.surfaces'):
        print(k, 'PC', [(hex(a), b - a) for a, b in ps[k]],
              'WU', [(hex(a), b - a) for a, b in ws[k]])

    (p_vd0a, p_vd0b), (p_vd1a, p_vd1b) = ps['draw.vd.data']
    (w_vd0a, w_vd0b), (w_vd1a, w_vd1b) = ws['draw.vd.data']
    p_ia, p_ib = ps['draw.indices'][0]
    p_sa, p_sb = ps['dpvs.surfaces'][0]
    w_sa, w_sb = ws['dpvs.surfaces'][0]
    nsurf = (p_sb - p_sa) // 80
    nidx = (p_ib - p_ia) // 2
    idx = struct.unpack_from('<%dH' % nidx, pc, p_ia)
    VD0_SIZE = p_vd0b - p_vd0a
    VD1_SIZE = p_vd1b - p_vd1a
    assert VD0_SIZE == w_vd0b - w_vd0a and VD1_SIZE == w_vd1b - w_vd1a

    # sanity: geometry fields of surfaces identical PC vs WU
    mm = 0
    g0, g1 = {}, {}
    for i in range(nsurf):
        po, wo = p_sa + i * 80, w_sa + i * 80
        f = {}
        for name, off, fmt in (('off0', 12, 'I'), ('off1', 28, 'I'),
                               ('tri', 42, 'H'), ('bidx', 44, 'I')):
            a = struct.unpack_from('<' + fmt, pc, po + off)[0]
            b = struct.unpack_from('>' + fmt, wu, wo + off)[0]
            if a != b:
                mm += 1
                break
            f[name] = a
        else:
            if f['tri'] and f['bidx'] + f['tri'] * 3 <= nidx:
                vc = max(idx[f['bidx']:f['bidx'] + f['tri'] * 3]) + 1
                if f['off0'] not in g0 or vc > g0[f['off0']]:
                    g0[f['off0']] = vc
                if f['off1'] not in g1 or vc > g1[f['off1']]:
                    g1[f['off1']] = vc
    print('surfaces=%d geom-field-mismatch=%d vd0 groups=%d (sum vc=%d) vd1 groups=%d'
          % (nsurf, mm, len(g0), sum(g0.values()), len(g1)))

    fields = [('pos', 0, 12, 4), ('w', 12, 16, 4), ('color', 16, 20, 0),
              ('normal', 20, 24, 2), ('uv', 24, 32, 4), ('tangent', 32, 36, 2)]
    match = Counter()
    tot = 0
    tang, norm = [], []
    skipped = 0
    for off, vc in sorted(g0.items()):
        if off + vc * 36 > VD0_SIZE:
            skipped += 1
            continue
        p0, w0 = p_vd0a + off, w_vd0a + off
        for v in range(vc):
            pb = pc[p0 + v * 36: p0 + v * 36 + 36]
            wb = wu[w0 + v * 36: w0 + v * 36 + 36]
            tot += 1
            for name, a, b, sw2 in fields:
                seg = pb[a:b]
                if sw2:
                    seg = b''.join(seg[i:i + sw2][::-1] for i in range(0, len(seg), sw2))
                if seg == wb[a:b]:
                    match[name] += 1
                elif name == 'tangent' and len(tang) < 5000:
                    tang.append((pb[32:36], wb[32:36]))
                elif name == 'normal' and len(norm) < 5000:
                    norm.append((pb[20:24], wb[20:24]))
    print('vd0 verts compared=%d (groups oob=%d)' % (tot, skipped))
    for name, *_ in fields:
        print('  %-8s exact %8d / %d  (%.2f%%)' % (name, match[name], tot,
                                                   100.0 * match[name] / tot))
    print('normal mismatches=%d samples:' % len(norm))
    for p, w in norm[:12]:
        print('  pc=%s wu=%s' % (p.hex(), w.hex()))
    print('tangent mismatches sampled=%d samples:' % len(tang))
    for p, w in tang[:30]:
        print('  pc=%s wu=%s' % (p.hex(), w.hex()))

    # ---- vd1 ----
    n_lo = n_hi = n_tot = 0
    diffs = Counter()
    samples = []
    for off, vc in sorted(g1.items()):
        if off + vc * 4 > VD1_SIZE:
            continue
        for v in range(vc):
            p = pc[p_vd1a + off + v * 4: p_vd1a + off + v * 4 + 4]
            w = wu[w_vd1a + off + v * 4: w_vd1a + off + v * 4 + 4]
            n_tot += 1
            pu = struct.unpack('<HH', p)
            wv = struct.unpack('>HH', w)
            if pu[0] == wv[0]:
                n_lo += 1
            else:
                diffs['lo:%+d' % (wv[0] - pu[0])] += 1
                if len(samples) < 16:
                    samples.append((off, v, pu, wv))
            if pu[1] == wv[1]:
                n_hi += 1
            else:
                diffs['hi:%+d' % (wv[1] - pu[1])] += 1
    print('vd1 verts=%d  u16[0] exact %d (%.2f%%)  u16[1] exact %d (%.2f%%)' %
          (n_tot, n_lo, 100.0 * n_lo / max(n_tot, 1), n_hi, 100.0 * n_hi / max(n_tot, 1)))
    print('vd1 diff deltas (top 20):', diffs.most_common(20))
    for off, v, pu, wv in samples:
        print('  grp@%d v%d pc=(%04x,%04x) wu=(%04x,%04x)' % (off, v, *pu, *wv))


if __name__ == '__main__':
    main()
