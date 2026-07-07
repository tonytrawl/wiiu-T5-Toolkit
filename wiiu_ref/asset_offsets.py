#!/usr/bin/env python3
"""
Dump (index, type, name, file_offset) for every asset in a decompressed WiiU T6 zone.

Walks the zone with walker.py; each asset's FILE offset comes from the walker's
ground-truth resync (type-aware next-body validation), so it stays exact even when
an individual asset's internal walk has a trailing gap. The asset NAME is the first
inline c-string consumed during the asset's walk — correct for every T6 asset root
(all ZoneCode reorders put `name` first; Material's info.name is field 0).

Output (tsv): index<TAB>typename<TAB>assetname<TAB>hex_file_offset

Usage: python asset_offsets.py <zone> <out.tsv>
"""
import sys, importlib

import walker as W
import struct_layout

def main():
    zpath, out_path = sys.argv[1], sys.argv[2]
    wz = importlib.import_module('wiiu_zone')
    zone = open(zpath, 'rb').read()
    r = wz.ZoneReader(zone); r.read_string_table(); r.read_asset_list()
    L = struct_layout.Layout(W.HDR, console=True)
    zc = W.ZoneCode(W.ZC_DIR)
    w = W.Walker(zone, L, zc, r.block_sizes)

    # capture the first c-string each asset's walk consumes (= the asset name)
    first_str = {'pos': None}
    orig_skip = w.skip_cstring
    def skip_hook(cur):
        if first_str['pos'] is None:
            first_str['pos'] = cur
        return orig_skip(cur)
    w.skip_cstring = skip_hook

    def next_body(nm_next, frm, window=8192):
        root_next = W.ASSET_ROOT.get(nm_next)
        if root_next is None:
            return None
        for g in range(0, window, 4):
            if w.is_plausible_body(root_next, frm + g):
                return frm + g
        return None

    def read_name(pos):
        if pos is None:
            return ''
        end = zone.index(b'\x00', pos)
        s = zone[pos:end]
        try:
            return s.decode('ascii')
        except UnicodeDecodeError:
            return ''

    rows = []
    cur = r.assets_end
    lost_at = None
    for i, (cid, pc, nm) in enumerate(r.assets):
        root = W.ASSET_ROOT.get(nm)
        start = cur
        first_str['pos'] = None
        if root is not None and root in L.structs:
            try:
                cur = w.walk(root, cur)
            except Exception:
                cur = start
        rows.append((i, nm or '?', read_name(first_str['pos']), start))
        if i < len(r.assets) - 1:
            pos = next_body(r.assets[i+1][2], cur)
            if pos is None:
                lost_at = i
                break
            cur = pos

    with open(out_path, 'w', encoding='utf-8') as f:
        for i, tnm, anm, off in rows:
            f.write("%d\t%s\t%s\t0x%x\n" % (i, tnm, anm, off))
    print("wrote %d rows -> %s" % (len(rows), out_path))
    if lost_at is not None:
        print("WARNING: resync LOST after asset %d/%d" % (lost_at, len(r.assets)))
    named = sum(1 for _, _, a, _ in rows if a)
    print("assets with a recovered name: %d/%d" % (named, len(rows)))

if __name__ == '__main__':
    main()
