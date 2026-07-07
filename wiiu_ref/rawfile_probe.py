#!/usr/bin/env python3
"""
RAWFILE console (Wii U v148) layout probe. Byte-exact.

FINDING: console RawFile is PC-IDENTICAL.
  body (12 bytes):
    +0 const char* name (FOLLOW)   +4 int len   +8 char* buffer (FOLLOW)
  consumption = 12 + strlen(name)+1 + (len + 1)   ['set count buffer len + 1']
  buffer[len] == 0 on every genuine asset. No alignment, no dropped members.
"""
import struct, re, sys, os

NAME_RE = re.compile(rb'[\w/.\- ]{3,120}\.[A-Za-z0-9_]{1,12}$')


def detect_endian(d):
    be = struct.unpack('>I', d[0:4])[0]
    le = struct.unpack('<I', d[0:4])[0]
    return '>' if abs(be - len(d)) < abs(le - len(d)) else '<'


def find_rawfiles(d, e):
    out = []
    ff = b'\xff\xff\xff\xff'
    pos = 0
    while True:
        pos = d.find(ff, pos)
        if pos < 0:
            break
        b = pos
        pos += 1
        if d[b+8:b+12] != ff:
            continue
        ln = struct.unpack(e + 'I', d[b+4:b+8])[0]
        if not (1 <= ln < 0x1000000):
            continue
        nul = d.find(b'\x00', b + 12, b + 12 + 128)
        if nul < 0:
            continue
        name = d[b+12:nul]
        if not NAME_RE.fullmatch(name):
            continue
        buf = nul + 1
        if buf + ln >= len(d) or d[buf + ln] != 0:
            continue
        # rawfile payloads are text-ish (gsc source, csv, vision, graph):
        # require mostly printable in the first 64 bytes
        head = d[buf:buf+min(64, ln)]
        if head and sum(32 <= c < 127 or c in (9, 10, 13) for c in head) < len(head) * 0.85:
            continue
        out.append((b, name.decode(), ln, buf))
    return out


def parse_rawfile(d, b, e):
    ln = struct.unpack(e + 'I', d[b+4:b+8])[0]
    nul = d.index(b'\x00', b + 12)
    return nul + 1 + ln + 1, d[b+12:nul].decode()


def main():
    zones = sys.argv[1:] or ['mp_raid_genuine.zone', 'zm_transit_original.zone',
                             '../PC ff/mp_raid.zone']
    for zp in zones:
        d = open(zp, 'rb').read()
        e = detect_endian(d)
        rfs = find_rawfiles(d, e)
        starts = {b for b, *_ in rfs}
        chained = sum(1 for b, n, ln, buf in rfs
                      if parse_rawfile(d, b, e)[0] in starts)
        print('%s [%s]: RAWFILE-like=%d chained-to-next=%d' %
              (os.path.basename(zp), 'BE' if e == '>' else 'LE',
               len(rfs), chained))
        for b, n, ln, buf in rfs[:40]:
            nxt = parse_rawfile(d, b, e)[0]
            print('    0x%08x len=%-7d %-52s %s' %
                  (b, ln, n, 'CHAIN' if nxt in starts else ''))


if __name__ == '__main__':
    main()
