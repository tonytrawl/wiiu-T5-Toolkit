#!/usr/bin/env python3
"""
POLISH probe v5: full-stream vd1 validation. Per-group stride from extent/vc in {4,8,12,16};
rule: element = (stride/4 - 1) f16-pair words (swap2) + final 4-byte quad (verbatim); stride-4
elements are a single swapped word. Unclean groups examined explicitly; uncovered gap bytes diffed.
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


def conv_elem(p, stride):
    out = b''
    nw = stride // 4
    for wo in range(nw):
        wbytes = p[wo * 4:wo * 4 + 4]
        if stride > 4 and wo == nw - 1:
            out += wbytes
        else:
            out += wbytes[0:2][::-1] + wbytes[2:4][::-1]
    return out


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
    stride = {}
    unclean = []
    for i, off in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else VD1
        ext = end - off
        vc = g1[off]
        if vc and ext % vc == 0 and ext // vc in (4, 8, 12, 16):
            stride[off] = (ext // vc, vc)
        else:
            unclean.append((off, vc, ext))
    print('clean groups=%d strides=%s unclean=%d' %
          (len(stride), Counter(s for s, _ in stride.values()), len(unclean)))
    for off, vc, ext in unclean:
        # is this offset inside/at the edge of another group's element grid?
        prev = max((o for o in stride if o < off), default=None)
        info = ''
        if prev is not None:
            s, pvc = stride[prev]
            info = 'prev grp@%d stride=%d vc=%d prev_end=%d rel_off=%d rel%%stride=%d' % (
                prev, s, pvc, prev + s * pvc, off - prev, (off - prev) % s)
        print('  UNCLEAN grp@%d vc=%d ext=%d  %s' % (off, vc, ext, info))

    # validate conversion over covered bytes; track coverage map
    cov = bytearray(VD1)
    ok = bad = 0
    badsam = []
    for off, (s, vc) in sorted(stride.items()):
        for v in range(vc):
            a = off + v * s
            p = pc[p1a + a:p1a + a + s]
            w = wu[w1a + a:w1a + a + s]
            exp = conv_elem(p, s)
            for j in range(s):
                cov[a + j] = 1
            if w == exp:
                ok += 1
            else:
                bad += 1
                if len(badsam) < 12:
                    badsam.append((off, s, v, p.hex(), w.hex(), exp.hex()))
    covered = sum(cov)
    print('elements ok=%d bad=%d  covered=%d/%d bytes' % (ok, bad, covered, VD1))
    for t in badsam:
        print('  grp@%d s%d v%d pc=%s wu=%s exp=%s' % t)
    # gap bytes: PC vs WU raw diff
    gap_same = gap_diff = 0
    gsam = []
    i = 0
    while i < VD1:
        if not cov[i]:
            if pc[p1a + i] == wu[w1a + i]:
                gap_same += 1
            else:
                gap_diff += 1
                if len(gsam) < 10:
                    gsam.append(i)
        i += 1
    print('gap bytes: same=%d diff=%d first-diffs=%s' % (gap_same, gap_diff, gsam))


if __name__ == '__main__':
    main()
