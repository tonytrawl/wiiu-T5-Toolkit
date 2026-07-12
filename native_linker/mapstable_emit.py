#!/usr/bin/env python3
"""
Emit a console (BE) StringTable asset body for zm/mapstable.csv containing all the
DLC zombies map rows, to be OVERRIDE-injected via a native zone (DB_LinkXAssetEntry
allows StringTable override; see HANDOFF session 4b).

Self-contained: every cell is FOLLOW-inline (no external aliases). Layout:
  {name* FOLLOW, u32 cols, u32 rows, values* FOLLOW, cellIndex* FOLLOW}
  inline name "zm/mapstable.csv\0"
  cells[rows*cols] = {u32 ptr=FOLLOW, u32 hash=djb2ci(str)}   (BE)
  string pool: each cell's string + NUL, in cell order
  cellIndex[rows*cols] int16 BE = sorted(range(n), key=signed hash asc)

Rows mirror PC retail (patch_zm zm/mapstable), trimmed to WiiU's 19 columns
(PC's 20th col = compass position, dropped by WiiU). Meta rows (header/maxnum_map/
default) are carried from the genuine WiiU table verbatim.
"""
import struct

ASSET_NAME = b'zm/mapstable.csv'
FOLLOW = 0xFFFFFFFF
COLS = 19


def djb2ci(s):
    h = 5381
    for c in s.encode('latin1', 'replace').lower():
        h = ((h * 33) + c) & 0xFFFFFFFF
    return h


def _sgn(h):
    return h - 0x100000000 if h >= 0x80000000 else h


# --- rows (19 cols each). PC retail values, col19 (compass pos) dropped. ---
# meta rows come from the genuine WiiU table; map rows from pc_zm_rows.json (trimmed).
HEADER = ['A0', 'b1', 'C2', 'bU', 'Cv', 'dw', 'g6', 'h7', 'i8', 'j9',
          'k10', 'l11', 'm12', 'n13', 'o14', 'p15', 'q16', '', '']

def _map(name, fA, fB, key, sign, idx, desc, comp, size, dlc,
         fAkey, fBkey, fAid, fBid, c16, c17):
    # 19 cols: 0 name,1 fA,2 fB,3 key,4 sign,5 idx,6 desc,7 comp,8 size,9 NO,
    # 10 YES,11 dlc,12 fAkey,13 fBkey,14 fAid,15 fBid,16 c16,17 c17,18 '0'
    return [name, fA, fB, key, sign, idx, desc, comp, size, 'NO', 'YES', dlc,
            fAkey, fBkey, fAid, fBid, c16, c17, '0']

MAP_ROWS = [
    _map('zm_transit', 'cdc', 'cia', 'ZMUI_TRANSIT', 'menu_zm_map_signpost_transit',
         '0', 'ZMUI_DESC_MAP_TRANSIT', 'compass_overlay_map_transit', 'SMALL', '0',
         'ZMUI_CDC_SHORT', 'ZMUI_CIA_SHORT', 'faction_cdc', 'faction_cia', '125', '46'),
    _map('zm_nuked', 'cdc', 'cia', 'ZMUI_NUKED', 'menu_zm_map_signpost_nuketown',
         '1', 'ZMUI_DESC_MAP_NUKED', 'compass_overlay_map_nuked', 'small', '2',
         'ZMUI_CDC_SHORT', 'ZMUI_CIA_SHORT', 'faction_cdc', 'faction_cia', '110', '2r'),
    _map('zm_highrise', 'cdc', 'cia', 'ZMUI_HIGHRISE', 'menu_zm_map_signpost_highrise',
         '2', 'ZMUI_DESC_MAP_HIGHRISE', 'compass_overlay_map_highrise', 'small', '3',
         'ZMUI_CDC_SHORT', 'ZMUI_CIA_SHORT', 'faction_cdc', 'faction_cia', '-100', '2r'),
    _map('zm_transit_dr', 'cdc', 'Zombie', 'ZMUI_TRANSIT', 'menu_zm_map_signpost_transit',
         '3', 'ZMUI_DESC_MAP_TRANSIT_DR', 'compass_overlay_map_transit', 'small', '3',
         'ZMUI_CDC_SHORT', 'ZMUI_ZOMBIE_SHORT', 'faction_cdc', 'faction_zombie', '125', '46'),
    _map('zm_prison', 'guards', 'inmates', 'ZMUI_PRISON', 'menu_zm_map_signpost_prison',
         '4', 'ZMUI_DESC_MAP_PRISON', 'compass_overlay_map_transit', 'small', '4',
         'ZMUI_GUARDS_SHORT', 'ZMUI_INMATES_SHORT', 'faction_guards', 'faction_inmates', '122', '35'),
    _map('zm_buried', 'cdc', 'cia', 'ZMUI_BURIED', 'menu_zm_map_signpost_buried',
         '5', 'ZMUI_DESC_MAP_BURIED', 'compass_overlay_map_highrise', 'small', '5',
         'ZMUI_CDC_SHORT', 'ZMUI_CIA_SHORT', 'faction_cdc', 'faction_cia', '-19', '-16'),
    _map('zm_tomb', 'cdc', 'cia', 'ZMUI_TOMB', 'menu_zm_map_signpost_tomb',
         '6', 'ZMUI_DESC_MAP_TOMB', 'compass_overlay_map_tomb', 'small', '6',
         'ZMUI_CDC_SHORT', 'ZMUI_CIA_SHORT', 'faction_cdc', 'faction_cia', '-11', '49'),
]

DEFAULT_ROW = ['default', 'cdc', 'cia'] + [''] * 16


def build_rows(maps=None):
    """maps: list of col0 names to include (default = all). Always transit first."""
    chosen = MAP_ROWS if maps is None else [r for r in MAP_ROWS if r[0] in maps]
    meta1 = ['maxnum_map', str(len(chosen))] + [''] * 17
    return [HEADER, meta1] + chosen + [DEFAULT_ROW]


def emit(rows, endian='>'):
    """rows: list of 19-string lists -> console StringTable body bytes."""
    nrows = len(rows)
    n = nrows * COLS
    flat = [rows[r][c] for r in range(nrows) for c in range(COLS)]
    hashes = [djb2ci(s) for s in flat]
    I = ('>I' if endian == '>' else '<I')
    h = 'h' if False else ('>h' if endian == '>' else '<h')
    body = bytearray()
    body += struct.pack(endian + 'I', FOLLOW)           # name*
    body += struct.pack(endian + 'I', COLS)             # columnCount
    body += struct.pack(endian + 'I', nrows)            # rowCount
    body += struct.pack(endian + 'I', FOLLOW)           # values*
    body += struct.pack(endian + 'I', FOLLOW)           # cellIndex*
    body += ASSET_NAME + b'\x00'                         # inline name
    for k in range(n):                                   # cells
        body += struct.pack(endian + 'II', FOLLOW, hashes[k])
    for k in range(n):                                   # string pool (cell order)
        body += flat[k].encode('latin1', 'replace') + b'\x00'
    order = sorted(range(n), key=lambda k: _sgn(hashes[k]))
    for idx in order:                                    # cellIndex int16
        body += struct.pack(endian + 'h', idx)
    return bytes(body)


if __name__ == '__main__':
    import sys, os
    rows = build_rows()
    blob = emit(rows, '>')
    out = sys.argv[1] if len(sys.argv) > 1 else 'zm_mapstable_allmaps.stbl'
    open(out, 'wb').write(blob)
    print('emitted %s: %d rows x %d cols, %d bytes' % (out, len(rows), COLS, len(blob)))
    # self-check: re-parse via mapstable_tool
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mapstable_tool as MT
    name, r, c, table, _b = MT.dump_stringtable(blob, 0, le=False)
    print('reparse: %s %dx%d' % (name, r, c))
    for row in table:
        print('  ', ' | '.join(x for x in row[:12]))
