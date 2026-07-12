#!/usr/bin/env python3
"""
POLISH probe v6: per-column vd1 analysis.
1. For each clean group and each 4-byte column: vote swap2 vs verbatim vs both vs neither
   against genuine console (ground truth).
2. PC-only detector: column is an f16 UV pair iff the high bytes of both u16 halves look like
   f16 sign+exponent (abs value decodes to a plausible UV magnitude) across the whole column;
   otherwise byte-quad. Compare detector vs ground truth.
"""
import struct
import sys
import os
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfxworld_assemble as GA


def get(n):
    m, d, cfg = GA.walk(n)
    spans = GA._spans(m, cfg['body'] + cfg['bodysize'])
    out = {}
    for k, a, b in spans:
        out.setdefault(k, []).append((a, b))
    return out, d


def f16_plausible_word(wbytes):
    """True if the 4 bytes look like two LE f16s with 'reasonable' magnitude (|x|<512 incl 0)."""
    for hb in (wbytes[1], wbytes[3]):
        e = (hb >> 2) & 0x1F          # exponent field of f16 from high byte
        if e == 0x1F:                 # inf/NaN
            return False
        if e > 0x17:                  # |x| >= 512 (exp>=0x17 -> 2^(23-15)=256.. allow up to)
            return False
    return True


def main():
    ps, pc = get('pc')
    ws, wu = get('wiiu')
    (_, _), (p1a, p1b) = ps['draw.vd.data']
    (_, _), (w1a, _) = ws['draw.vd.data']
    p_ia, p_ib = ps['draw.indices'][0]
    p_sa, p_sb = ps['dpvs.surfaces'][0]
    nidx = (p_ib - p_ia) // 2
    idx = struct.unpack_from('<%dH' % nidx, pc, p_ia)
    VD1 = p1b - p1a

    g1 = defaultdict(int)
    for i in range((p_sb - p_sa) // 80):
        po = p_sa + i * 80
        o1 = struct.unpack_from('<I', pc, po + 28)[0]
        tri = struct.unpack_from('<H', pc, po + 42)[0]
        bi = struct.unpack_from('<I', pc, po + 44)[0]
        if tri and bi + tri * 3 <= nidx:
            vc = max(idx[bi:bi + tri * 3]) + 1
            g1[o1] = max(g1[o1], vc)
    offs = sorted(g1)
    table = []
    agree = disagree = 0
    profiles = Counter()
    for i, off in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else VD1
        ext = end - off
        vc = g1[off]
        if not (vc and ext % vc == 0 and ext // vc in (4, 8, 12, 16)):
            continue
        s = ext // vc
        ncol = s // 4
        gt, det = [], []
        for c in range(ncol):
            swp = ver = nei = 0
            plaus = True
            for v in range(vc):
                a = off + v * s + c * 4
                p = pc[p1a + a:p1a + a + 4]
                w = wu[w1a + a:w1a + a + 4]
                sw = p[0:2][::-1] + p[2:4][::-1]
                if w == sw and w == p:
                    pass
                elif w == sw:
                    swp += 1
                elif w == p:
                    ver += 1
                else:
                    nei += 1
                if not f16_plausible_word(p):
                    plaus = False
            if nei:
                gt.append('X')
            elif swp and ver:
                gt.append('?')
            elif ver:
                gt.append('V')
            elif swp:
                gt.append('S')
            else:
                gt.append('A')      # all ambiguous
            det.append('S' if plaus else 'V')
        # ground-truth 'A' columns match either way; count agreement on decisive cols
        for c in range(ncol):
            if gt[c] in ('S', 'V'):
                if gt[c] == det[c]:
                    agree += 1
                else:
                    disagree += 1
                    table.append((off, s, vc, c, gt, det))
        profiles[(s, ''.join(gt), ''.join(det))] += 1
    print('column profiles (stride, ground-truth, detector) -> group count:')
    for k, v in sorted(profiles.items()):
        print('   s=%-2d gt=%-4s det=%-4s : %d' % (k[0], k[1], k[2], v))
    print('decisive columns agree=%d disagree=%d' % (agree, disagree))
    for off, s, vc, c, gt, det in table[:15]:
        print('  DISAGREE grp@%d s%d vc=%d col%d gt=%s det=%s' % (off, s, vc, c, gt, det))
        for v in range(min(vc, 6)):
            a = off + v * s + c * 4
            print('     pc=%s wu=%s' % (pc[p1a + a:p1a + a + 4].hex(),
                                        wu[w1a + a:w1a + a + 4].hex()))


if __name__ == '__main__':
    main()
