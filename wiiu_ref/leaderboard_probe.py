#!/usr/bin/env python3
"""
LEADERBOARD console (Wii U v148) layout probe.

FINDING: console LeaderboardDef is PC-IDENTICAL.
  LeaderboardDef body (36 bytes):
    +0  const char* name (FOLLOW)
    +4  u32 id   +8 int columnCount   +12 int dwColumnCount
    +16 int xpColId   +20 int prestigeColId
    +24 LbColumnDef* columns (FOLLOW)
    +28 u32 updateType   +32 int trackTypes
  then: name chars, then columnCount x LbColumnDef (44 bytes):
    +0 const char* name (FOLLOW)  +4 colId  +8 dwColIndex  +12 hidden(int)
    +16 const char* statName (FOLLOW)  +20 type  +24 precision  +28 agg
    +32 const char* localization (FOLLOW)  +36 uiCalColX  +40 uiCalColY
  array rule: all 44-byte column bodies first, then per column the
  name/statName/localization strings in member order.
"""
import struct, re, sys, os

FOLLOW = 0xFFFFFFFF
PTRS = (FOLLOW, 0xFFFFFFFE)
NAME_RE = re.compile(rb'[\w]{3,64}$')
COL = 44


def detect_endian(d):
    be = struct.unpack('>I', d[0:4])[0]
    le = struct.unpack('<I', d[0:4])[0]
    return '>' if abs(be - len(d)) < abs(le - len(d)) else '<'


def parse_lb(d, b, e):
    (name_p, lbid, cc, dwcc, xp, pr, cols_p, upd, trk) = \
        struct.unpack(e + '9I', d[b:b+36])
    o = b + 36
    nul = d.index(b'\x00', o)
    name = d[o:nul].decode()
    o = nul + 1
    cols = []
    if cols_p in PTRS:
        base = o
        o += cc * COL
        for i in range(cc):
            cb = base + i * COL
            cn, colid, dwi, hid, sn, ty, prec, agg, loc, ux, uy = \
                struct.unpack(e + '11I', d[cb:cb+COL])
            strs = []
            for p in (cn, sn, loc):
                if p in PTRS:
                    nul = d.index(b'\x00', o)
                    strs.append(d[o:nul].decode('latin-1'))
                    o = nul + 1
                else:
                    strs.append(None)
            cols.append((strs, colid, ty))
    return o, name, (lbid, cc, dwcc), cols


def find_lb(d, e):
    out = []
    pos = 0
    ff = b'\xff\xff\xff\xff'
    while True:
        pos = d.find(ff, pos)
        if pos < 0:
            break
        b = pos
        pos += 1
        try:
            v = struct.unpack(e + '9I', d[b:b+36])
        except struct.error:
            continue
        if v[6] not in PTRS:
            continue
        if not (0 < v[2] <= 64 and 0 <= v[3] <= 64 and v[2] >= v[3]):
            continue
        nul = d.find(b'\x00', b + 36, b + 100)
        if nul <= b + 36 or not NAME_RE.fullmatch(d[b+36:nul]):
            continue
        # column 0 must look like an LbColumnDef (name ptr FOLLOW/null)
        cb = nul + 1
        c0 = struct.unpack(e + 'I', d[cb:cb+4])[0]
        if c0 not in PTRS and c0 != 0:
            continue
        out.append(b)
    return out


def main():
    for zp in sys.argv[1:] or ['zm_transit_original.zone',
                               '../PC ff/zm_nuked.zone']:
        d = open(zp, 'rb').read()
        e = detect_endian(d)
        found = find_lb(d, e)
        print('%s [%s]: leaderboard candidates=%d' %
              (os.path.basename(zp), 'BE' if e == '>' else 'LE', len(found)))
        for b in found:
            try:
                end, name, hdr, cols = parse_lb(d, b, e)
            except Exception as ex:
                print('    0x%08x parse fail: %s' % (b, ex))
                continue
            nxt = struct.unpack(e + 'I', d[end:end+4])[0]
            ok = nxt == FOLLOW or nxt >= 0x80000000
            print('    0x%08x %-28s id=%d cols=%d end=0x%08x next=%08x %s' %
                  (b, name, hdr[0], hdr[1], end, nxt,
                   'RESYNC' if ok else 'BAD'))
            for strs, colid, ty in cols[:4]:
                print('        col %-24s stat=%-24s loc=%s' % tuple(strs))


if __name__ == '__main__':
    main()
