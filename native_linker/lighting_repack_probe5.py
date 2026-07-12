#!/usr/bin/env python3
"""
POLISH probe v7: correlate vd1 group column-profile (ground truth vs genuine console) with the
surfaces' MATERIAL NAMES (resolved via loader_sim PC runtime-alias inverse map).
Goal: a PC-only rule (material name grammar -> vd1 element layout) usable on no-oracle maps.
"""
import struct
import sys
import os
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfxworld_assemble as GA
import loader_sim as LS

PC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PC ff', 'mp_raid.zone')


def get(n):
    m, d, cfg = GA.walk(n)
    spans = GA._spans(m, cfg['body'] + cfg['bodysize'])
    out = {}
    for k, a, b in spans:
        out.setdefault(k, []).append((a, b))
    return out, d


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

    print('running PC loader sim (alias inverse map)...')
    em, spans, PCZ = LS.simulate_pc(PC_PATH)
    inv = LS.InverseMap(em.omap)
    B5 = 0xa0000000

    def mat_name(alias):
        if not (0xa0000000 <= alias < 0xc0000000):
            return None
        st = inv.stream(alias - B5) + LS.B5_BASE if hasattr(LS, 'B5_BASE') else None
        return st

    # LS.B5_BASE existence check
    b5base = getattr(LS, 'B5_BASE')
    surf_mats = {}

    g1 = defaultdict(int)
    gsurf = defaultdict(list)
    for i in range((p_sb - p_sa) // 80):
        po = p_sa + i * 80
        o1 = struct.unpack_from('<I', pc, po + 28)[0]
        tri = struct.unpack_from('<H', pc, po + 42)[0]
        bi = struct.unpack_from('<I', pc, po + 44)[0]
        mat = struct.unpack_from('<I', pc, po + 48)[0]
        if tri and bi + tri * 3 <= nidx:
            vc = max(idx[bi:bi + tri * 3]) + 1
            g1[o1] = max(g1[o1], vc)
            gsurf[o1].append(mat)

    def resolve_mat(alias):
        if alias in surf_mats:
            return surf_mats[alias]
        nm = None
        if 0xa0000000 <= alias < 0xc0000000:
            st = inv.stream(alias - B5) + b5base
            # Material body 112B; name ptr @0 FOLLOW -> name string after body
            try:
                namep = struct.unpack_from('<I', PCZ, st)[0]
                if namep in (0xFFFFFFFF, 0xFFFFFFFE):
                    e = PCZ.index(b'\x00', st + 112)
                    nm = PCZ[st + 112:e].decode('latin-1', 'replace')
            except Exception:
                nm = None
        surf_mats[alias] = nm
        return nm

    offs = sorted(g1)
    rows = []
    for i, off in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else VD1
        ext = end - off
        vc = g1[off]
        if not (vc and ext % vc == 0 and ext // vc in (4, 8, 12, 16)):
            continue
        s = ext // vc
        gt = []
        for c in range(s // 4):
            swp = ver = nei = 0
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
            gt.append('X' if nei else ('?' if (swp and ver) else
                      'V' if ver else 'S' if swp else 'A'))
        names = sorted({resolve_mat(m) or ('raw:%08x' % m) for m in gsurf[off]})
        rows.append((s, ''.join(gt), off, vc, names))

    # aggregate: does material-name prefix predict the profile?
    agg = defaultdict(Counter)
    for s, gt, off, vc, names in rows:
        for n in names:
            # grammar token: strip trailing hash: mc_lit_sm_b0c0_xxxx -> lit_sm_b0c0 features
            base = n.split('_')
            tok = '_'.join(x for x in base if len(x) == 2 and x[0] in 'bclrsdopqetnv' and x[1].isdigit())
            agg[(s, gt)][tok or n] += 1
    for k in sorted(agg):
        print('stride=%d gt=%s :' % k)
        for tok, cnt in agg[k].most_common(12):
            print('    %-40s %d' % (tok, cnt))
    # dump a few full rows for eyeballing
    print('\nsample rows:')
    for s, gt, off, vc, names in rows[:1000]:
        if s >= 8:
            print('  s%d gt=%s grp@%d vc=%d mats=%s' % (s, gt, off, vc, names[:3]))


if __name__ == '__main__':
    main()
