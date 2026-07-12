#!/usr/bin/env python3
"""
DIAG stage 2: label the SOURCE FIELD of every techset-interior tagged fixup.

Reads the rows JSON from diag_ts_interior.py, re-walks each source asset's PC
structure, and maps each candidate field offset to a struct-field label:
  XModel: body[+o] / bonedata / surf-hdr[+o] / surf-dyn / mat-handle /
          inline-mtl[+o] / collsurf[+o] / boneinfo / physpreset / tail
  Material: mtl[+o] labeled per convert_material layout
Aggregates (root, field-label, target-region) and reports, per family, whether
the referencing field is a REAL pointer field (per converter semantics) or a
data word misread (disposition 1 vs 2/3).

Usage: python diag_ts_fields.py <pc_zone> <rows.json>
"""
import sys, json, struct
from collections import Counter

import xmodel_convert as XC
import xmodel_pc as XP
import material_convert as MCV
import techset_pc

FOLLOW = 0xFFFFFFFF
PTRS = (FOLLOW, 0xFFFFFFFE)
B5_BASE = 64


def _u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def material_regions(d, off, tag, regs):
    """convert_material-mirroring labeled walk. Returns next offset."""
    PC_MAT = 112
    texc, constc, sbc = d[off + 84], d[off + 85], d[off + 86]
    ts, tt, ct, sbt, th = (_u32(d, off + 92 + k * 4) for k in range(5))
    regs.append((off, off + PC_MAT, tag + ':mtl-body'))
    src = off + PC_MAT
    if _u32(d, off) in PTRS:
        e = d.index(b'\x00', src) + 1
        regs.append((src, e, tag + ':mtl-name'))
        src = e
    if ts in PTRS:
        nxt = techset_pc.parse_techset_pc(d, src)
        regs.append((src, nxt, tag + ':mtl-inline-ts'))
        src = nxt
    if tt in PTRS:
        regs.append((src, src + texc * 16, tag + ':mtl-texdefs'))
        base = src
        src += texc * 16
        for i in range(texc):
            if _u32(d, base + i * 16 + 12) in PTRS:
                e = MCV.pc_image_span(d, src)
                regs.append((src, e, tag + ':mtl-inline-img'))
                src = e
    if ct in PTRS:
        regs.append((src, src + constc * 32, tag + ':mtl-constdefs'))
        src += constc * 32
    if sbt in PTRS:
        regs.append((src, src + sbc * 20, tag + ':mtl-statebits'))
        src += sbc * 20
    if th in PTRS:
        src = material_regions(d, src, tag + ':thermal', regs)
    return src


def xmodel_regions(d, off):
    """Labeled sub-regions of a PC XModel span: [(s, e, label)]."""
    regs = []
    nb, nrb, ns = d[off + 4], d[off + 5], d[off + 6]
    ncoll = _u32(d, off + 156)
    regs.append((off, off + 248, 'xm-body'))
    _, cur = XC.convert_xmodel_bonedata(d, off)
    regs.append((off + 248, cur, 'xm-bonedata'))
    c = cur
    if _u32(d, off + 32) in PTRS:
        sb = c
        regs.append((sb, sb + ns * 80, 'xm-surfhdr'))
        cc = [sb + ns * 80]
        for i in range(ns):
            s0 = cc[0]
            XP._surface_dyn(d, sb + i * 80, cc)
            regs.append((s0, cc[0], 'xm-surfdyn'))
        c = cc[0]
    if _u32(d, off + 36) in PTRS:
        base = c
        regs.append((base, base + 4 * ns, 'xm-mathandle'))
        c += 4 * ns
        for i in range(ns):
            if _u32(d, base + i * 4) in PTRS:
                c = material_regions(d, c, 'xm', regs)
    if _u32(d, off + 152) in PTRS:
        base = c
        regs.append((base, base + 44 * ncoll, 'xm-collsurf'))
        c += 44 * ncoll
        for i in range(ncoll):
            cs = base + i * 44
            if _u32(d, cs) in PTRS:
                n = _u32(d, cs + 4) * 48
                regs.append((c, c + n, 'xm-colltris'))
                c += n
    if _u32(d, off + 164) in PTRS:
        regs.append((c, c + 44 * nb, 'xm-boneinfo'))
        c += 44 * nb
    if _u32(d, off + 200) in PTRS:
        c += 4 * ns
    if _u32(d, off + 216) in PTRS:
        regs.append((c, c + 84, 'xm-physpreset'))
        # strings after — coarse
    return regs


def label_at(regs, o):
    for (s, e, lab) in regs:
        if s <= o < e:
            return lab, o - s
    return 'xm-tail?', -1


def main():
    pc_path, rows_path = sys.argv[1], sys.argv[2]
    PC = open(pc_path, 'rb').read()
    rows = json.load(open(rows_path))

    # source asset spans: need asset start offsets. Recover from pc_zone walk.
    import produce_nobackbone as PN
    bodies, _ = PN.walk_pc_bodies(PC)
    span_by_idx = {i: (s, e, root, nm) for (i, nm, root, s, e, hp) in bodies
                   if s is not None}

    xm_cache = {}
    agg = Counter()
    detail = Counter()
    unlabeled = []
    for r in rows:
        i = r['src_idx']
        sp = span_by_idx.get(i)
        if sp is None:
            agg[(r['root'], 'no-span', r['region'])] += 1
            continue
        s, e, root, nm = sp
        labs = set()
        for f in r['fields']:
            fo = s + f
            if root == 'XModel':
                if s not in xm_cache:
                    try:
                        xm_cache[s] = xmodel_regions(PC, s)
                    except Exception as ex:
                        xm_cache[s] = []
                lab, ro = label_at(xm_cache[s], fo)
            elif root == 'Material':
                regs = []
                try:
                    material_regions(PC, s, 'm', regs)
                except Exception:
                    pass
                lab, ro = label_at(regs, fo)
            else:
                lab, ro = root.lower(), f
            # refine per-field offsets for fixed-size records
            if lab == 'xm-surfhdr':
                lab += '+%d' % (ro % 80)
            elif lab == 'xm-body':
                lab += '+%d' % ro
            elif lab.endswith('mtl-body'):
                lab += '+%d' % ro
            elif lab == 'xm-mathandle':
                lab += '[k]'
            elif lab == 'xm-collsurf':
                lab += '+%d' % (ro % 44)
            labs.add(lab)
        key = (root, '|'.join(sorted(labs)) or '-nofield-', r['region'])
        agg[key] += 1
        if not labs:
            unlabeled.append(r)
    print('(root, source-field(s), target-region) -> count')
    for k, n in agg.most_common(50):
        print('  %-12s %-42s %-13s %d' % (k[0], k[1][:42], k[2], n))
    if unlabeled:
        print('\nunlabeled examples:')
        for r in unlabeled[:5]:
            print(' ', r)


if __name__ == '__main__':
    main()
