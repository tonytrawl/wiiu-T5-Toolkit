#!/usr/bin/env python3
"""
POLISH probe: SndBank loadedAssets blob, genuine console vs PC (mp_raid).
Walks the SndBank body (layout from wiiu_ref/sndbank_probe.py) far enough to capture the
positions of the loadedAssets ENTRY table (entryCount x SndAssetBankEntry 20B) and DATA blob,
then cross-maps PC->console entries by id and compares metadata + per-entry format headers.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)
ALIASLIST, ALIAS, RADVERB, DUCK = 20, 100, 100, 76


def parse(d, b, e, body=4756):
    """Like sndbank_probe.parse_sndbank but returns the entries/data spans."""
    def u32(o):
        return struct.unpack(e + 'I', d[o:o + 4])[0]
    name_p, aliasCount, alias_p, aliasIndex_p, radverbCount, radverbs_p, \
        duckCount, ducks_p = struct.unpack(e + '8I', d[b:b + 32])
    o = b + body
    name = None
    if name_p in PTRS:
        nul = d.index(b'\x00', o)
        name = d[o:nul].decode('latin-1')
        o = nul + 1
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
                    for po in (a + 0, a + 8, a + 12, a + 20):
                        if u32(po) in PTRS:
                            o = d.index(b'\x00', o) + 1
    if aliasIndex_p in PTRS:
        o += aliasCount * 4
    if radverbs_p in PTRS:
        o += radverbCount * RADVERB
    if ducks_p in PTRS:
        base = o
        o += duckCount * DUCK
        for i in range(duckCount):
            db = base + i * DUCK
            for po in (db + 64, db + 68):
                if u32(db + 64 - db + db + (po - db)) in PTRS:
                    pass
            for po in (db + 64, db + 68):
                if u32(po) in PTRS:
                    o += 32 * 4
    for po in range(32, 0x126c, 4):
        if u32(b + po) == FOLLOW:
            o = d.index(b'\x00', o) + 1
    loadedCount = u32(b + 0x126c)
    entryCount = u32(b + 0x1270)
    dataSize = u32(b + 0x1278)
    entries_at = data_at = None
    if u32(b + 0x1274) == FOLLOW:
        entries_at = o
        o += entryCount * 20
    if u32(b + 0x127c) == FOLLOW:
        data_at = o
        o += dataSize
    return dict(name=name, loadedCount=loadedCount, entryCount=entryCount,
                dataSize=dataSize, entries_at=entries_at, data_at=data_at, end=o)


def entries(d, at, n, e):
    out = []
    for i in range(n):
        o = at + i * 20
        eid, size, off, fc = struct.unpack_from(e + '4I', d, o)
        fri, ch, loop, fmt = struct.unpack_from('4B', d, o + 16)
        out.append(dict(id=eid, size=size, offset=off, frames=fc,
                        rate_idx=fri, channels=ch, looping=loop, fmt=fmt))
    return out


def main():
    wu = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
    pc = open(os.path.join('..', 'PC ff', 'mp_raid.zone'), 'rb').read()
    W = parse(wu, 0x45bea9e, '>')
    P = parse(pc, 0x5bcc5a6, '<')
    for tag, r in (('WU', W), ('PC', P)):
        print('%s bank %-16s loaded=%d entries=%d dataSize=%d entries@%s data@%s' %
              (tag, r['name'], r['loadedCount'], r['entryCount'], r['dataSize'],
               hex(r['entries_at'] or 0), hex(r['data_at'] or 0)))
    ew = entries(wu, W['entries_at'], W['entryCount'], '>')
    ep = entries(pc, P['entries_at'], P['entryCount'], '<')
    from collections import Counter
    print('WU formats:', Counter(x['fmt'] for x in ew), ' rates:', Counter(x['rate_idx'] for x in ew),
          'ch:', Counter(x['channels'] for x in ew))
    print('PC formats:', Counter(x['fmt'] for x in ep), ' rates:', Counter(x['rate_idx'] for x in ep),
          'ch:', Counter(x['channels'] for x in ep))
    pid = {x['id']: x for x in ep}
    matched = sum(1 for x in ew if x['id'] in pid)
    print('id match: %d / %d WU entries found in PC (%d PC entries)' % (matched, len(ew), len(ep)))
    # order comparison: WU ids sequence vs PC filtered sequence
    pcseq = [x['id'] for x in ep if x['id'] in {y['id'] for y in ew}]
    wuseq = [x['id'] for x in ew]
    print('same order:', pcseq == wuseq)
    # offsets: monotonic? relative to data start? alignment?
    print('WU first 5 entries:', ew[:5])
    print('PC first 5 entries:', [pid.get(x['id']) for x in ew[:5]])
    # per-entry header check: format-9 blob magic
    for x in ew[:5]:
        blob = wu[W['data_at'] + x['offset']: W['data_at'] + x['offset'] + 16]
        print('WU blob @+%d head: %s' % (x['offset'], blob.hex()))
    # frames vs PC frames; size arithmetic
    rows = []
    for x in ew:
        p = pid.get(x['id'])
        if p:
            rows.append((x, p))
    fr_same = sum(1 for x, p in rows if x['frames'] == p['frames'])
    ch_same = sum(1 for x, p in rows if x['channels'] == p['channels'])
    lp_same = sum(1 for x, p in rows if x['looping'] == p['looping'])
    rate_pairs = Counter((p['rate_idx'], x['rate_idx']) for x, p in rows)
    print('frames equal: %d/%d, channels %d, looping %d; rate pairs: %s' %
          (fr_same, len(rows), ch_same, lp_same, rate_pairs))


if __name__ == '__main__':
    main()
