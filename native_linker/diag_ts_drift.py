#!/usr/bin/env python3
"""
DIAG stage 3: test the MIS-INVERSION hypothesis for techset-interior tags.

If the PC loader does NOT consume runtime memory for techset shader bytecode
(temp-loaded), pc_inv (built from a stream-length model) inverts runtime
addresses of objects AFTER a techset into the techset's stream span. Then for
each tagged fixup, the TRUE stream target should be at b5 + D where D is the
accumulated under-consumption — and D should be consistent per techset and
reconstructible from the techset's own structure (sum of prog sizes before
the landing point, etc.).

Test per row (mathandle family): scan forward from the tagged b5 for the next
inline-Material root signature (FOLLOW name ptr + plausible body) and report
the distance and whether distance == sum of shader-prog bytes between b5 and
the techset end (or similar structural quantity).

Usage: python diag_ts_drift.py <pc_zone> <rows.json>
"""
import sys, json, struct
from collections import Counter
import techset_pc
from diag_ts_interior import labeled_techset_regions, region_at

B5_BASE = 64
FOLLOW = 0xFFFFFFFF
PTRS = (FOLLOW, 0xFFFFFFFE)


def _u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def main():
    pc_path, rows_path = sys.argv[1], sys.argv[2]
    PC = open(pc_path, 'rb').read()
    rows = json.load(open(rows_path))

    # per-techset labeled regions + prog-byte prefix sums
    reg_cache = {}

    stats = Counter()
    ex = {}
    for r in rows:
        foff = r['pc_b5'] + B5_BASE
        # find enclosing techset via the ts name start: re-derive from regions
        # (rows carry ts name only; rebuild by scanning: cache by ts name)
        key = r['ts']
        # locate techset start: search PC for name + walk — instead reuse pc walk
        stats[(r['region'], 'rows')] += 1

    # Rebuild techset spans once (name -> (start, end, regions))
    import produce_nobackbone as PN
    bodies, _ = PN.walk_pc_bodies(PC)
    ts_list = [(s, e, nm) for (i, nm, root, s, e, hp) in bodies
               if root == 'MaterialTechniqueSet' and s is not None]
    ts_regs = {}
    for (s, e, nm) in ts_list:
        try:
            ts_regs[s] = labeled_techset_regions(PC, s)
        except Exception:
            ts_regs[s] = []

    def enclosing_ts(foff):
        for (s, e, nm) in ts_list:
            if s <= foff < e:
                return s, e, nm
        return None

    out = Counter()
    drift_per_ts = {}
    for r in rows:
        foff = r['pc_b5'] + B5_BASE
        ts = enclosing_ts(foff)
        if ts is None:
            out['no-enclosing-ts'] += 1
            continue
        s, e, nm = ts
        # structural quantity A: prog bytes from foff to techset end
        prog_after = sum(min(re_, e) - max(rs, foff)
                         for (rs, re_, lab) in ts_regs[s]
                         if lab.endswith('-prog') and re_ > foff)
        # structural quantity B: prog bytes from techset START to foff
        prog_before = sum(min(re_, foff) - rs
                          for (rs, re_, lab) in ts_regs[s]
                          if lab.endswith('-prog') and rs < foff)
        # candidate true target if progs are PC-temp: stream pos that has
        # runtime address == foff's model address happens LATER by prog_after
        # within this techset, then beyond. For a first look just record how
        # far the techset end is and what sits right after.
        d_end = e - foff
        nxt16 = PC[e:e + 16].hex()
        out[('rows-with-ts',)] += 1
        drift_per_ts.setdefault(nm, []).append(
            (r['root'], r.get('region'), foff - s, d_end, prog_after, prog_before))

    print(dict(out))
    # For each techset with tagged rows: are landing offsets == (true target
    # offset - prog_before)? Print a few samples with structure.
    n = 0
    for nm, lst in drift_per_ts.items():
        print('\n== %s  (%d rows)' % (nm, len(lst)))
        for t in lst[:4]:
            print('   src=%-12s reg=%-13s off-in-ts=%-8d to-end=%-8d '
                  'prog_after=%-8d prog_before=%d' % t)
        n += 1
        if n >= 8:
            break


if __name__ == '__main__':
    main()
