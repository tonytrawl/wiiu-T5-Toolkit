#!/usr/bin/env python3
"""
DIAG (assemble pass 3): decompose the unres:techset-interior class per-FIELD.

For every tagged fixup, records:
  - SOURCE: which asset was emitting (idx/name/root) and WHERE in the PC source
    span the raw alias value sits (candidate referencing field offsets),
  - TARGET: which techset, which labeled region inside it (shader hdr/name/prog,
    vdecl, args row, literal float4, tech hdr/name), the 16 bytes at the target,
    and whether the target parses as a C-string.

Aggregates into (source root, field family, target region kind) so each family
can get its positive predicate (dispositions: data-noise / content-dedup
re-source / substitution-model gap).

Usage: python diag_ts_interior.py <pc_zone> [out.json]
"""
import sys, os, json, struct
import produce_nobackbone as PN
import techset_pc as TS

B5_BASE = 64


def labeled_techset_regions(d, off):
    """Labeled walk mirroring techset_pc.parse_techset_pc: [(s, e, label)]."""
    regs = []
    PTRS = TS.PTRS
    u32, u16 = TS._u32, TS._u16
    o = off + TS.TS_BODY
    regs.append((off, o, 'ts-body'))
    if u32(d, off) in PTRS:
        e = d.index(b'\x00', o) + 1
        regs.append((o, e, 'ts-name'))
        o = e
    for i in range(36):
        if u32(d, off + 8 + i * 4) not in PTRS:
            continue
        tb = o
        pass_count = u16(d, tb + 6)
        o = tb + TS.TECH_HDR + pass_count * TS.PASS
        regs.append((tb, o, 'tech-hdr'))
        for p in range(pass_count):
            pb = tb + TS.TECH_HDR + p * TS.PASS
            if u32(d, pb + 4) in PTRS:                 # vertexShader
                regs.append((o, o + 16, 'vshader-hdr'))
                e = o + 16
                if u32(d, o) in PTRS:
                    e2 = d.index(b'\x00', e) + 1
                    regs.append((e, e2, 'vshader-name'))
                    e = e2
                if u32(d, o + 8) in PTRS:
                    ps = u32(d, o + 12)
                    regs.append((e, e + ps, 'vshader-prog'))
                    e += ps
                o = e
            if u32(d, pb + 0) in PTRS:                 # vertexDecl
                regs.append((o, o + TS.VDECL, 'vdecl'))
                o += TS.VDECL
            if u32(d, pb + 8) in PTRS:                 # pixelShader
                regs.append((o, o + 16, 'pshader-hdr'))
                e = o + 16
                if u32(d, o) in PTRS:
                    e2 = d.index(b'\x00', e) + 1
                    regs.append((e, e2, 'pshader-name'))
                    e = e2
                if u32(d, o + 8) in PTRS:
                    ps = u32(d, o + 12)
                    regs.append((e, e + ps, 'pshader-prog'))
                    e += ps
                o = e
            if u32(d, pb + 20) in PTRS:                # args
                argc = d[pb + 12] + d[pb + 13] + d[pb + 14]
                abase = o
                o += argc * TS.ARG
                regs.append((abase, o, 'args'))
                for a in range(argc):
                    ab = abase + a * TS.ARG
                    if u16(d, ab) in TS.MTL_ARG_LITERAL and u32(d, ab + 8) in PTRS:
                        regs.append((o, o + 16, 'literal16'))
                        o += 16
        if u32(d, tb) in PTRS:                          # technique name (LAST)
            e = d.index(b'\x00', o) + 1
            regs.append((o, e, 'tech-name'))
            o = e
    return regs


def region_at(regs, foff):
    for (s, e, lab) in regs:
        if s <= foff < e:
            return lab, foff - s, e - foff
    return '?past-end', -1, -1


def cstr_at(PC, foff):
    try:
        e = PC.index(b'\x00', foff, foff + 96)
    except ValueError:
        return None
    s = PC[foff:e]
    if len(s) < 3 or any(c < 0x20 or c > 0x7e for c in s):
        return None
    return s.decode('ascii')


def main():
    path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    PN.TS_TRACE = True
    import loader_sim as LS
    pol = LS.derive_pc_policy(path)
    stat, out_assets, omap = PN.assemble_zone(path, verbose=False, pc_policy=pol)
    PC = omap.PC
    trace = omap.ts_trace or []
    print('tagged techset-interior fixups (final pass): %d' % len(trace))

    # span lookup for source assets
    spans = {(ps, root): (ps, pe) for (ps, pe, root) in (omap.pc_spans or [])}

    reg_cache = {}
    rows = []
    for (ctx, v, b5, ts_s, ts_e) in trace:
        i, nm, root, s = ctx
        foff = b5 + B5_BASE
        if ts_s not in reg_cache:
            try:
                reg_cache[ts_s] = labeled_techset_regions(PC, ts_s + B5_BASE)
            except Exception as ex:
                reg_cache[ts_s] = []
        lab, roff, rem = region_at(reg_cache[ts_s], foff)
        # techset name
        tsn = cstr_at(PC, ts_s + B5_BASE + TS.TS_BODY) or '?'
        # candidate referencing field offsets in the source asset PC span
        fields = []
        sp = spans.get((s - B5_BASE, root))
        if sp and root != 'GfxWorld':
            needle = struct.pack('<I', v)
            base = sp[0] + B5_BASE
            end = sp[1] + B5_BASE
            j = PC.find(needle, base, end)
            while j >= 0 and len(fields) < 8:
                fields.append(j - base)
                j = PC.find(needle, j + 1, end)
        tgt16 = PC[foff:foff + 16].hex()
        cs = cstr_at(PC, foff)
        rows.append(dict(src_idx=i, src=nm, root=root, v='0x%08x' % v,
                         pc_b5=b5, ts=tsn, region=lab, roff=roff,
                         fields=fields, tgt16=tgt16, cstr=cs))

    # aggregate
    from collections import Counter
    agg = Counter((r['root'], r['region']) for r in rows)
    print('\n(source root, target region) -> count')
    for k, n in agg.most_common():
        print('  %-18s %-14s %d' % (k[0], k[1], n))
    aggf = Counter()
    for r in rows:
        fs = ','.join(str(f % 4096) for f in r['fields'][:2]) or '-'
        aggf[(r['root'], r['region'], len(r['fields']))] += 1
    print('\n(source root, region, n-candidate-fields) -> count')
    for k, n in aggf.most_common(30):
        print('  %-18s %-14s nf=%d  %d' % (k[0], k[1], k[2], n))

    if out_path:
        json.dump(rows, open(out_path, 'w'), indent=1)
        print('\nwrote %s (%d rows)' % (out_path, len(rows)))


if __name__ == '__main__':
    main()
