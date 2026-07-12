#!/usr/bin/env python3
"""Empirically derive per-field endian transform for SndAlias(100) / SndAliasList(20) /
SndRadverb(100) / SndDuck(76) by walking genuine raid (BE) and PC raid (LE) banks in
parallel and, for each 4-byte word, checking whether genuine == swap32/swap16/verbatim
of the PC word across ALL structs of that type. Emits a per-word transform vector."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S

FOLLOW = 0xFFFFFFFF; INSERT = 0xFFFFFFFE; PTRS = (FOLLOW, INSERT)

GEN = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
PC  = open(os.path.join('..', 'PC ff', 'mp_raid.zone'), 'rb').read()
GB0 = 0x45bea9e
PB0 = 0x5bcc5a6


def collect(d, b, e, body=S.BODY):
    """Walk one bank; return dict class->list of (abs_offset) for each struct, plus end."""
    u32 = lambda o: struct.unpack(e + 'I', d[o:o+4])[0]
    name_p, aliasCount, alias_p, aliasIndex_p, radverbCount, radverbs_p, \
        duckCount, ducks_p = struct.unpack(e + '8I', d[b:b+32])
    o = b + body
    rec = {'ALIASLIST': [], 'ALIAS': [], 'RADVERB': [], 'DUCK': []}
    if name_p in PTRS:
        o = d.index(b'\x00', o) + 1
    if alias_p in PTRS:
        base = o; o += aliasCount * S.ALIASLIST
        for i in range(aliasCount):
            lb = base + i * S.ALIASLIST
            rec['ALIASLIST'].append(lb)
            lname_p, lid, head_p, cnt, seq = struct.unpack(e + '5I', d[lb:lb+20])
            if lname_p in PTRS:
                o = d.index(b'\x00', o) + 1
            if head_p in PTRS:
                ab = o; o += cnt * S.ALIAS
                for k in range(cnt):
                    a = ab + k * S.ALIAS
                    rec['ALIAS'].append(a)
                    for po in (a+0, a+8, a+12, a+20):
                        if u32(po) in PTRS:
                            o = d.index(b'\x00', o) + 1
    if aliasIndex_p in PTRS:
        o += aliasCount * 4
    if radverbs_p in PTRS:
        base = o; o += radverbCount * S.RADVERB
        for i in range(radverbCount):
            rec['RADVERB'].append(base + i * S.RADVERB)
    if ducks_p in PTRS:
        base = o; o += duckCount * S.DUCK
        for i in range(duckCount):
            db = base + i * S.DUCK
            rec['DUCK'].append(db)
            for po in (db+64, db+68):
                if u32(po) in PTRS:
                    o += 32 * 4
    # tail: body zone/language strings, entries, data, scriptIdLookups
    for po in range(32, 0x126c, 4):
        if u32(b + po) == FOLLOW:
            o = d.index(b'\x00', o) + 1
    entryCount = u32(b + 0x1270); dataSize = u32(b + 0x1278)
    if u32(b + 0x1274) == FOLLOW:
        o += entryCount * 20
    if u32(b + 0x127c) == FOLLOW:
        o += dataSize
    cnt = u32(b + 0x1280)
    if u32(b + 0x1284) == FOLLOW:
        o += cnt * 8
    return rec, o


def word(d, o):
    return d[o:o+4]

def sw32(b): return b[::-1]
def sw16(b): return b[0:2][::-1] + b[2:4][::-1]


def derive(cls, size, gen_rec, pc_rec):
    goffs = gen_rec[cls]; poffs = pc_rec[cls]
    assert len(goffs) == len(poffs), (cls, len(goffs), len(poffs))
    n = len(goffs)
    print('\n=== %s  (%d structs, %d words) ===' % (cls, n, size // 4))
    trans = []
    for w in range(0, size, 4):
        c32 = c16 = cver = cnone = 0
        for gi, pi in zip(goffs, poffs):
            gw = word(GEN, gi + w); pw = word(PC, pi + w)
            if gw == sw32(pw): c32 += 1
            elif gw == sw16(pw): c16 += 1
            elif gw == pw: cver += 1
            else: cnone += 1
        # decide (swap32 and swap16 coincide when both halves symmetric; prefer verbatim if all)
        best = max(('swap32', c32), ('swap16', c16), ('verbatim', cver),
                   ('MISMATCH', cnone), key=lambda x: x[1])
        # refine: if verbatim covers all, it's verbatim regardless
        tag = best[0]
        note = 'ok'
        if cnone > 0 and best[0] != 'MISMATCH':
            note = 'PARTIAL cnone=%d' % cnone
        if best[0] == 'MISMATCH':
            note = 'UNKNOWN (name-hash?)'
        print('  +%3d  swap32=%-5d swap16=%-5d verbatim=%-5d none=%-5d -> %-8s %s'
              % (w, c32, c16, cver, cnone, tag, note))
        trans.append((w, tag, c32, c16, cver, cnone))
    return trans


# genuine raid has two banks: bank[0] small localized, bank[1] big (matches PC).
_r0, gb1 = collect(GEN, GB0, '>')
print('genuine bank[0] end / bank[1] start = 0x%08x' % gb1)
gen_rec, gend = collect(GEN, gb1, '>')
pc_rec, pcend = collect(PC, PB0, '<')
print('gen end=0x%08x  pc end=0x%08x' % (gend, pcend))
for cls, count in [('ALIASLIST', len(gen_rec['ALIASLIST'])),
                   ('ALIAS', len(gen_rec['ALIAS'])),
                   ('RADVERB', len(gen_rec['RADVERB'])),
                   ('DUCK', len(gen_rec['DUCK']))]:
    print('  %-10s gen=%d pc=%d' % (cls, count, len(pc_rec[cls])))

derive('ALIASLIST', S.ALIASLIST, gen_rec, pc_rec)
derive('ALIAS', S.ALIAS, gen_rec, pc_rec)
derive('RADVERB', S.RADVERB, gen_rec, pc_rec)
derive('DUCK', S.DUCK, gen_rec, pc_rec)
