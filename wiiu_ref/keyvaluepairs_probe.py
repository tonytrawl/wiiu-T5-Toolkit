#!/usr/bin/env python3
"""
KEYVALUEPAIRS console (Wii U v148) layout probe. Byte-exact.

FINDING: console KeyValuePairs is PC-IDENTICAL.
  KeyValuePairs body (12 bytes):
    +0 const char* name (FOLLOW)  +4 u32 numVariables  +8 KeyValuePair* (FOLLOW)
  then: name chars, then numVariables x KeyValuePair (12 bytes each):
    +0 u32 keyHash  +4 u32 namespaceHash  +8 const char* value (FOLLOW)
  (array rule: all pair bodies first, then each pair's value string in order)

  KVP is always asset[0], so its body sits exactly at the end of the asset
  index array; the probe verifies the walk lands exactly on the next asset
  body (Glasses/other, which starts with a FOLLOW name pointer).
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiiu_zone

FOLLOW = 0xFFFFFFFF


def parse_kvp(d, b, e):
    name_p, num, pairs_p = struct.unpack(e + '3I', d[b:b+12])
    o = b + 12
    name = None
    if name_p == FOLLOW:
        nul = d.index(b'\x00', o)
        name = d[o:nul].decode()
        o = nul + 1
    pairs = []
    if pairs_p == FOLLOW:
        base = o
        o += num * 12
        for i in range(num):
            kh, nh, vp = struct.unpack(e + '3I', d[base+i*12:base+i*12+12])
            v = None
            if vp == FOLLOW:
                nul = d.index(b'\x00', o)
                v = d[o:nul].decode('latin-1')
                o = nul + 1
            pairs.append((kh, nh, v))
    return o, name, pairs


def main():
    for zp in sys.argv[1:] or ['mp_raid_genuine.zone',
                               'zm_transit_original.zone']:
        d = open(zp, 'rb').read()
        z = wiiu_zone.ZoneReader(d)
        z.read_string_table()
        z.read_asset_list()
        assert z.assets[0][2] == 'KEYVALUEPAIRS'
        b = z.assets_end
        end, name, pairs = parse_kvp(d, b, '>')
        nxt = struct.unpack('>I', d[end:end+4])[0]
        ok = nxt == FOLLOW      # next asset body starts with FOLLOW name ptr
        print('%s: KVP @0x%x name=%s pairs=%d end=0x%x next-u32=%08x %s' %
              (os.path.basename(zp), b, name, len(pairs), end, nxt,
               'LANDS ON NEXT ASSET' if ok else 'BAD'))
        for kh, nh, v in pairs[:6]:
            print('    key=%08x ns=%08x value=%r' % (kh, nh, v))


if __name__ == '__main__':
    main()
