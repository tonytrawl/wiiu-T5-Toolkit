#!/usr/bin/env python3
"""
FOOTSTEP_TABLE / FOOTSTEPFX_TABLE console (Wii U v148) layout probe.

FINDING: both are PC-IDENTICAL in layout.
  FootstepTableDef (900 bytes):
    +0 const char* name (FOLLOW -> chars inline after the 900-byte body,
       or an alias if the identical string was already written)
    +4 u32 sndAliasTable[32][7] (896 bytes)
    consumption = 900 + (strlen(name)+1 if name ptr is FOLLOW else 0).
  NOTE: the 896-byte alias-hash table is BYTE-IDENTICAL between the PC and
  Wii U zones (the hash words are not endian-swapped in the file).
  FootstepFXTableDef (132 bytes):
    +0 const char* name (FOLLOW)
    +4 FxEffectDef* footstepFX[32] (asset refs; genuine zones hold only
       null/alias here, so no inline data)
    consumption = 132 + strlen(name)+1.

Verified: the 7-table mp_raid run and 6-table zm_transit run chain
hard (each record ends exactly at the next record's body) on Wii U and PC.
"""
import struct, re, sys, os

FOLLOW = 0xFFFFFFFF
NAME_RE = re.compile(rb'[a-z][a-z0-9_]{3,48}$')


def detect_endian(d):
    be = struct.unpack('>I', d[0:4])[0]
    le = struct.unpack('<I', d[0:4])[0]
    return '>' if abs(be - len(d)) < abs(le - len(d)) else '<'


def parse_table(d, b, e):
    """Returns (end, name) or None if b cannot be a FootstepTableDef body."""
    if b + 900 > len(d):
        return None
    np = struct.unpack(e + 'I', d[b:b+4])[0]
    if np == FOLLOW:
        nul = d.find(b'\x00', b + 900, b + 950)
        if nul <= b + 900 or not NAME_RE.fullmatch(d[b+900:nul]):
            return None
        return nul + 1, d[b+900:nul].decode()
    if np >= 0x80000000 and np != FOLLOW:        # alias name (block-tagged)
        return b + 900, '<alias:%08x>' % np
    return None


def find_chains(d, e, min_len=2):
    """Anchor on FOLLOW-named tables, then chain forward."""
    anchors = []
    pos = 0
    ff = b'\xff\xff\xff\xff'
    while True:
        pos = d.find(ff, pos)
        if pos < 0:
            break
        b = pos
        pos += 1
        r = parse_table(d, b, e)
        if r and r[1][0] != '<':
            anchors.append(b)
    chains = []
    used = set()
    for a in anchors:
        if a in used:
            continue
        chain = []
        b = a
        while True:
            r = parse_table(d, b, e)
            if r is None:
                break
            chain.append((b, r[1]))
            used.add(b)
            b = r[0]
        real = sum(1 for _, nm in chain if nm[0] != '<')
        if len(chain) >= min_len and real >= 3:
            chains.append((chain, b))
    return chains


def main():
    for zp in sys.argv[1:] or ['mp_raid_genuine.zone',
                               'zm_transit_original.zone',
                               '../PC ff/mp_raid.zone']:
        d = open(zp, 'rb').read()
        e = detect_endian(d)
        chains = find_chains(d, e)
        print('%s [%s]: footstep chains: %d' %
              (os.path.basename(zp), 'BE' if e == '>' else 'LE', len(chains)))
        for chain, end in chains:
            for b, nm in chain:
                print('    0x%08x %s' % (b, nm))
            nxt = struct.unpack(e + 'I', d[end:end+4])[0]
            print('    -> chain end 0x%08x next-u32=%08x' % (end, nxt))


if __name__ == '__main__':
    main()
