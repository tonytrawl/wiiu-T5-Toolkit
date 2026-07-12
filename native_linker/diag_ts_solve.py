#!/usr/bin/env python3
"""
DIAG stage 4: solve the corrected stream target of each techset-interior tag
under the hypothesis "PC shader prog bytes (and optionally shader/tech name
strings) are TEMP on PC (consume no runtime)".

Model: rt_true(x) = rt_model(x) - P(x), P = prefix sum of temp-class bytes in
techset spans before stream offset x. Given a tagged runtime value v_rt, find
x with rt_true(x) = v_rt (monotone; binary search over sorted omap keys with
correction), then classify the bytes at x.

Usage: python diag_ts_solve.py <pc_zone> <rows.json> [progs|progs+names]
"""
import sys, json, struct, bisect
from collections import Counter
import loader_sim as LS
import produce_nobackbone as PN
from diag_ts_interior import labeled_techset_regions, cstr_at

B5_BASE = 64
FOLLOW = 0xFFFFFFFF
PTRS = (FOLLOW, 0xFFFFFFFE)


def _u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def main():
    pc_path, rows_path = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else 'progs'
    PC = open(pc_path, 'rb').read()
    rows = json.load(open(rows_path))

    pol = LS.derive_pc_policy(pc_path)
    em, spans, _ = LS.simulate_pc(PC, verbose=False, policy=pol)
    omap = em.omap                       # stream b5 -> runtime b5 (model)
    ks = sorted(omap)

    bodies, _ = PN.walk_pc_bodies(PC)
    # temp-class spans (stream b5): shader progs (+ names in mode 2)
    temp = []
    labs_want = ('-prog',) if mode == 'progs' else ('-prog', '-name', 'ts-name')
    for (i, nm, root, s, e, hp) in bodies:
        if root != 'MaterialTechniqueSet' or s is None:
            continue
        try:
            regs = labeled_techset_regions(PC, s)
        except Exception:
            continue
        for (rs, re_, lab) in regs:
            if any(lab.endswith(w) for w in labs_want):
                temp.append((rs - B5_BASE, re_ - B5_BASE))
    temp.sort()
    # prefix sums
    tstarts = [t[0] for t in temp]
    pref = [0]
    for (a, b) in temp:
        pref.append(pref[-1] + (b - a))

    def P(x):
        i = bisect.bisect_right(tstarts, x) - 1
        if i < 0:
            return 0
        a, b = temp[i]
        return pref[i] + min(max(x - a, 0), b - a)

    def rt_true(x):
        # model rt of stream x via nearest omap key at/below x
        j = bisect.bisect_right(ks, x) - 1
        if j < 0:
            return None
        base = ks[j]
        return omap[base] + (x - base) - P(x)

    # binary search x in [0, max stream] such that rt_true(x) == target
    hi_x = ks[-1]

    def solve(vrt):
        lo, hi = 0, hi_x
        while lo < hi:
            mid = (lo + hi) // 2
            r = rt_true(mid)
            if r is None or r < vrt:
                lo = mid + 1
            else:
                hi = mid
        return lo

    # asset span lookup for classification
    spans_l = [(s - B5_BASE, e - B5_BASE, root, nm) for (i, nm, root, s, e, hp)
               in bodies if s is not None and e]
    sstarts = [t[0] for t in spans_l]

    def span_of(x):
        j = bisect.bisect_right(sstarts, x) - 1
        if j >= 0 and spans_l[j][0] <= x < spans_l[j][1]:
            return spans_l[j]
        return None

    agg = Counter()
    samples = {}
    for r in rows:
        vrt = (int(r['v'], 16) - 1) & 0x1FFFFFFF
        x = solve(vrt)
        sp = span_of(x)
        foff = x + B5_BASE
        b16 = PC[foff:foff + 16]
        looks_mtl = _u32(PC, foff) in PTRS or (0xA0000000 <=
                                               _u32(PC, foff) <= 0xBFFFFFFF)
        cs = cstr_at(PC, foff)
        key = (r['root'], r['region'], sp[2] if sp else '?',
               'mtl-sig' if looks_mtl else ('str' if cs else 'bin'))
        agg[key] += 1
        if key not in samples:
            samples[key] = (r['src'], r['v'], x, sp and sp[3], b16.hex(), cs,
                            r['pc_b5'], x - r['pc_b5'])
    print('corrected-target classes: (src-root, old-region, new-span-root, sig)')
    for k, n in agg.most_common(40):
        print('  %-11s %-13s %-22s %-8s %d' % (k[0], k[1], k[2], k[3], n))
    print('\nsamples:')
    for k, s in list(samples.items())[:25]:
        print(' ', k, '->', s)


if __name__ == '__main__':
    main()
