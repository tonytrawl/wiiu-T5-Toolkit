#!/usr/bin/env python3
"""
zm additive edit with SAFE DISPLAY columns (isolated side project).

Same as patch_relink cmd_edit --tag zm (adds zm_prison/zm_buried/zm_tomb rows), but
the 3 new rows REUSE an existing stock map's display-asset columns so every referenced
material/image/loc key is guaranteed to exist in the console zone. This isolates the
"missing DLC display asset stalls the zombie menu build" hypothesis: if the menu now
appears and lists 3 extra maps (showing the reference map's art but LOADING the DLC
map), the stall was the missing display assets, not the zone link.

Kept columns on the new rows: col0 internal name, col5 map index, col11 DLC pack index,
col8/9/10 size/flags. All other columns copied from the reference stock row REF_MAP.

Run from native_linker/:
  python "../dlc loading/native/fullrelink/zm_edit_safedisplay.py"
"""
import sys, os, struct

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
for _p in (os.path.join(_ROOT, 'native_linker'), os.path.join(_ROOT, 'wiiu_ref'),
           os.path.join(_ROOT, 'WiiU_FF_Studio'), os.path.join(_ROOT, 'tools'),
           os.path.join(_ROOT, 'dlc loading', 'native')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(os.path.join(_ROOT, 'native_linker'))

import wiiu_ff, wiiu_zone, struct_layout
import walker as W
import zone_stream as zs
import stage1_roundtrip as S1
import patch_relink as PR

REF_MAP = 'zm_transit'          # existing stock map whose display columns we borrow
KEEP_COLS = {0, 5, 8, 9, 10}   # keep identity/index/flags; borrow display incl pack

CON = os.path.join(_ROOT, 'dlc loading', 'native', 'upd_patch_zm.ff')
PC  = os.path.join(_ROOT, 'dlc loading', 'native', 'pc_authentic', 'pc_patch_zm.ff')
OUT = os.path.join(_ROOT, 'dlc loading', 'native', 'fullrelink', '_zm_borrow_pack0')


def main():
    zone = PR.load_zone(CON)
    r = PR.inventory(zone)
    needle = b'zm/mapstable.csv'
    chdr, ccols, crows = PR._st_header(zone, needle, le=False)
    ccols, crows, con_table = PR.read_table(zone, chdr, le=False)

    # console mapstable body span (to skip in source)
    name_end = zone.index(b'\x00', chdr + 20); cells0 = name_end + 1
    n = ccols * crows; o = cells0 + n * 8
    for k in range(n):
        p, _h = struct.unpack_from('>2I', zone, cells0 + k*8)
        if p == 0xFFFFFFFF:
            o = zone.index(b'\x00', o) + 1
    con_body_end = o + n * 2

    pc = PR._decrypt_pc(PC)
    phdr, pcols, prows = PR._st_header(pc, needle, le=True)
    _pc, _pr, pc_table = PR.read_table(pc, phdr, le=True)

    merged, new_rows = PR.build_console_maprows(con_table, pc_table, ccols, 'zm_', 'zm')
    ref = next(r for r in con_table if r and r[0] == REF_MAP)
    # rewrite the new rows' display columns from REF_MAP (keep identity/index cols)
    newnames = {row[0] for row in new_rows}
    patched = 0
    for row in merged:
        if row and row[0] in newnames:
            for c in range(ccols):
                if c not in KEEP_COLS:
                    row[c] = ref[c] if c < len(ref) else ''
            patched += 1
    for row in merged:
        if row and row[0] in newnames:
            while len(row)<=11: row.append('')
            row[11]='0'
    print('added %d new zm rows, display borrowed from %s: %s'
          % (patched, REF_MAP, ', '.join(sorted(newnames))))

    new_body = PR.emit_stringtable(merged, ccols, 'zm/mapstable.csv')
    delta = len(new_body) - (con_body_end - chdr)
    print('   mapstable %d B -> %d B (delta +%d)' % (con_body_end - chdr, len(new_body), delta))

    # ---- identical emit machinery to PR.cmd_edit (2-pass relink + header/XAssetList) ----
    L = struct_layout.Layout(W.HDR, console=True); zc = W.ZoneCode(W.ZC_DIR)

    def emit_pass(omap0):
        w = zs.ZoneWriter(); w.push_block(zs.BLOCK_VIRTUAL)
        w.block_size[zs.BLOCK_VIRTUAL] = r.assets_end - PR.B5_BASE
        em = PR.EditEmitter(zone, L, zc, w, chdr, con_body_end, new_body)
        em.delta = delta; em.shift_from = con_body_end - PR.B5_BASE
        if omap0 is not None:
            em.omap.update(omap0)
        em.subbed = False
        cur = r.assets_end; wb = None
        for (cid, pc_, nm) in r.assets:
            root = W.ASSET_ROOT.get(nm)
            if root is None or root not in L.structs:
                continue
            try:
                cur = em.emit_asset(root, cur)
            except Exception as ex:
                wb = (nm, cur, str(ex)[:60]); break
        return em, w, cur, wb

    em1, _w1, _c1, _b1 = emit_pass(None)
    em, w, cur, wb = emit_pass(em1.omap)
    if not em.subbed:
        raise RuntimeError('substitution never fired: %r' % (wb,))
    if cur < len(zone):
        w.write_bytes(zone[cur:])
    c = S1.parse_container(zone)
    c['size'] += delta
    c['block_sizes'][zs.BLOCK_VIRTUAL] += delta
    edited = bytearray(S1.emit_container(c)[:r.assets_end] + bytes(w.buf))
    shift_from = con_body_end - PR.B5_BASE
    ao = r.assets_off; nhp = 0
    for i in range(r.asset_count):
        ho = ao + i*8 + 4
        h = struct.unpack_from('>I', edited, ho)[0]
        if 0xA0000001 <= h <= 0xBFFFFFFF:
            blk, off = zs.decode_ptr(h)
            if blk == zs.BLOCK_VIRTUAL and off >= shift_from:
                struct.pack_into('>I', edited, ho, zs.encode_ptr(blk, off + delta)); nhp += 1
    edited = bytes(edited)

    r2 = wiiu_zone.ZoneReader(edited); r2.read_string_table(); r2.read_asset_list()
    e2 = PR._st_header(edited, needle, le=False)
    cc, rr, t2 = PR.read_table(edited, e2[0], le=False)
    names2 = [row[0] for row in t2 if row and row[0].startswith('zm_')]
    print('   re-read edited: %d zm maps (%s)' % (len(names2), names2))

    ff = wiiu_ff.pack(edited, PR.orig_ff_name(CON))
    os.makedirs(OUT, exist_ok=True)
    outp = os.path.join(OUT, 'patch_zm.ff')
    open(outp, 'wb').write(ff)
    print('   packed %d B -> %s' % (len(ff), outp))


if __name__ == '__main__':
    main()
