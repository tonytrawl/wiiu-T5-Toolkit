#!/usr/bin/env python3
"""
POLISH probe 2: reconcile the zone loadedAssets entryCount/dataSize with the on-disc console
.sabl entry tables via the alias assetIds. Zone tables are RUNTIME-FILLED (all zeros in genuine);
the linker only authored entryCount + dataSize. Establish the exact arithmetic.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'WiiU_FF_Studio'))
import sab_convert as SC

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)
ALIASLIST, ALIAS, RADVERB, DUCK = 20, 100, 100, 76


def aliases(d, b, e, body=4756):
    """Yield (assetId, flags_lo, flags_hi, assetFileName or None) for every alias."""
    def u32(o):
        return struct.unpack(e + 'I', d[o:o + 4])[0]
    name_p, aliasCount, alias_p = struct.unpack(e + '3I', d[b:b + 12])
    o = b + body
    if name_p in PTRS:
        o = d.index(b'\x00', o) + 1
    out = []
    if alias_p in PTRS:
        base = o
        o += aliasCount * ALIASLIST
        for i in range(aliasCount):
            lb = base + i * ALIASLIST
            lname_p, lid, head_p, cnt, seq = struct.unpack(e + '5I', d[lb:lb + ALIASLIST])
            if lname_p in PTRS:
                o = d.index(b'\x00', o) + 1
            if head_p in PTRS:
                ab = o
                o += cnt * ALIAS
                for k in range(cnt):
                    a = ab + k * ALIAS
                    assetId = u32(a + 16)
                    f0, f1 = u32(a + 24), u32(a + 28)
                    strs = {}
                    for tag, po in (('name', 0), ('sub', 8), ('sec', 12), ('file', 20)):
                        if u32(a + po) in PTRS:
                            nul = d.index(b'\x00', o)
                            strs[tag] = d[o:nul].decode('latin-1')
                            o = nul + 1
                    out.append((assetId, f0, f1, strs.get('file')))
    return out


def main():
    wu = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
    al = aliases(wu, 0x45c04a5, '>')
    print('aliases parsed: %d, with assetFileName: %d, unique assetIds(nonzero): %d' %
          (len(al), sum(1 for a in al if a[3]), len({a[0] for a in al if a[0]})))
    ids = {a[0] for a in al if a[0]}

    banks = {}
    root = r'E:\Wii U Black ops 2\content\sound'
    for nm in ('loaded\\mpl_raid.all.sabl', 'loaded\\mpl_common.all.sabl',
               'loaded\\default_mp.all.sabl', 'loaded\\cmn_root.all.sabl',
               'mpl_raid.all.sabs', 'mpl_common.all.sabs', 'default_mp.all.sabs',
               'cmn_root.all.sabs'):
        try:
            banks[nm] = SC.SabFile(os.path.join(root, nm))
        except Exception as ex:
            print('  (skip %s: %s)' % (nm, ex))

    total_cnt = 0
    total_size = 0
    total_align8 = 0
    seen = set()
    for nm, sab in banks.items():
        hit = [e for e in sab.entries if e.id in ids and e.id not in seen]
        for e in hit:
            seen.add(e.id)
        ssum = sum(e.size for e in hit)
        a8 = sum((e.size + 7) & ~7 for e in hit)
        print('%-28s entries=%5d matched=%4d sum=%9d align8=%9d' %
              (nm, len(sab.entries), len(hit), ssum, a8))
        if nm.endswith('.sabl'):
            total_cnt += len(hit)
            total_size += ssum
            total_align8 += a8
    print('TOTAL loaded matched: count=%d sum=%d align8=%d' % (total_cnt, total_size, total_align8))
    print('zone says:            count=654 dataSize=11519896')


if __name__ == '__main__':
    main()
