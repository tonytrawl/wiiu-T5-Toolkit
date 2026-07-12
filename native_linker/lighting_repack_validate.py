#!/usr/bin/env python3
"""
Validator for lighting_repack: byte-exact vs genuine console on mp_raid AND mp_dockside.
vd0: whole stream converted group-aware (grouped vertices via conv_world_vertex36, inter-group
     padding verbatim) and compared byte-for-byte over group-covered bytes + padding report.
vd1: conv_vd1 (group/column rule + last-column vote) compared byte-for-byte over the stream.
"""
import struct
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfxworld_assemble as GA
import gfxworld_probe2 as G2
import lighting_repack as LR

# dockside CFG (bodies located via loader_sim spans, 2026-07-10)
G2.CFG['pc_dockside'] = dict(G2.CFG['pc'], path='../wiiu_ref/mp_dockside_pc.zone',
                             body=0x35a3b03)
G2.CFG['wiiu_dockside'] = dict(G2.CFG['wiiu'], path='mp_dockside_wiiu.zone',
                               body=0x27256a7)


def get(n):
    m, d, cfg = GA.walk(n)
    spans = GA._spans(m, cfg['body'] + cfg['bodysize'])
    out = {}
    for k, a, b in spans:
        out.setdefault(k, []).append((a, b))
    return out, d


def validate(pcname, wuname, label, wu_vd0=None):
    """wu_vd0: explicit genuine-console vd0 start when the console walker drifts (DLC maps);
    vd1 is contiguous after vd0 (raid-verified layout: vd0 then vd1)."""
    print('=== %s ===' % label)
    ps, pc = get(pcname)
    ws, wu = get(wuname)
    vd = ps['draw.vd.data']
    if len(vd) < 2:
        print('  !! walk did not yield 2 vd spans:', vd)
        return
    (p0a, p0b), (p1a, p1b) = vd
    if wu_vd0 is not None:
        w0a = wu_vd0
        w0b = w0a + (p0b - p0a)
        w1a, w1b = w0b, w0b + (p1b - p1a)
    else:
        (w0a, w0b), (w1a, w1b) = ws['draw.vd.data']
    p_ia, p_ib = ps['draw.indices'][0]
    p_sa, p_sb = ps['dpvs.surfaces'][0]
    VD0, VD1 = p0b - p0a, p1b - p1a
    assert VD0 == w0b - w0a and VD1 == w1b - w1a, 'stream size mismatch PC vs WU'
    nsurf = (p_sb - p_sa) // 80
    nidx = (p_ib - p_ia) // 2
    idx = struct.unpack_from('<%dH' % nidx, pc, p_ia)

    # ---- vd0 ----
    g0 = {}
    for i in range(nsurf):
        po = p_sa + i * 80
        o0 = struct.unpack_from('<I', pc, po + 12)[0]
        tri = struct.unpack_from('<H', pc, po + 42)[0]
        bi = struct.unpack_from('<I', pc, po + 44)[0]
        if tri and bi + tri * 3 <= nidx:
            vc = max(idx[bi:bi + tri * 3]) + 1
            if vc > g0.get(o0, 0):
                g0[o0] = vc
    ok = bad = 0
    badf = Counter()
    for off, vc in sorted(g0.items()):
        if off + vc * 36 > VD0:
            continue
        conv = LR.conv_world_vertex36(pc[p0a + off:p0a + off + vc * 36])
        gen = wu[w0a + off:w0a + off + vc * 36]
        if conv == gen:
            ok += vc
        else:
            for v in range(vc):
                a, b = v * 36, v * 36 + 36
                if conv[a:b] == gen[a:b]:
                    ok += 1
                else:
                    bad += 1
                    for name, fa, fb in (('pos', 0, 12), ('w', 12, 16), ('color', 16, 20),
                                         ('normal', 20, 24), ('uv', 24, 32), ('tangent', 32, 36)):
                        if conv[a + fa:a + fb] != gen[a + fa:a + fb]:
                            badf[name] += 1
    print('vd0: verts exact %d, diverging %d (%.4f%% exact); per-field fails: %s'
          % (ok, bad, 100.0 * ok / max(ok + bad, 1), dict(badf) or 'none'))

    # ---- vd1 ----
    groups = LR.vd1_groups(pc, p_sa, nsurf, idx, nidx, VD1)
    strides = Counter(s for _, s, _ in groups)
    conv = LR.conv_vd1(pc[p1a:p1b], groups)
    gen = wu[w1a:w1b]
    diff = [i for i in range(VD1) if conv[i] != gen[i]]
    covered = bytearray(VD1)
    for off, s, vc in groups:
        for j in range(off, min(off + s * vc, VD1)):
            covered[j] = 1
    in_grp = sum(1 for i in diff if covered[i])
    print('vd1: %d bytes, groups=%d (strides %s), diff bytes=%d (in-group %d, gap %d)'
          % (VD1, len(groups), dict(strides), len(diff), in_grp, len(diff) - in_grp))
    if diff:
        for i in diff[:10]:
            print('   first diffs @%d: conv=%02x gen=%02x pc=%02x cov=%d'
                  % (i, conv[i], gen[i], pc[p1a + i], covered[i]))


if __name__ == '__main__':
    validate('pc', 'wiiu', 'mp_raid')
    # console walker drifts on the DLC map (region-order variance); vd0 anchored by
    # searching the genuine zone for the converted first PC vertex (verified 72B match)
    validate('pc_dockside', 'wiiu_dockside', 'mp_dockside', wu_vd0=0x2d9fe51)
