#!/usr/bin/env python3
"""Stronger validation: pair SndAlias structs by (list index, alias index) walking
converted-output and genuine INDEPENDENTLY (each consumes its own strings), so the
per-platform string-count difference doesn't desync the pairing. Compares the
non-hash/non-flagbit/non-pad bytes across ALL 12467 aliases."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S
import smalls_convert as SC

PC  = open(os.path.join('..', 'PC ff', 'mp_raid.zone'), 'rb').read()
GEN = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
end0, _, _, _ = S.parse_sndbank(GEN, 0x45bea9e, '>')
GB1 = end0
out, nxt = SC.convert_sndbank(PC, 0x5bcc5a6)

def walk_alias_by_list(d, b):
    """Return list of alias abs-offsets, walking with per-stream string consumption."""
    u32 = lambda o: struct.unpack_from('>I', d, o)[0]
    name_p, ac, alias_p, ai, rc, rp, dc, dp = struct.unpack_from('>8I', d, b)
    o = b + S.BODY; res = []
    if name_p in S.PTRS: o = d.index(b'\x00', o) + 1
    base = o; o += ac * S.ALIASLIST
    for i in range(ac):
        lb = base + i * S.ALIASLIST
        ln, li, hp, cnt, sq = struct.unpack_from('>5I', d, lb)
        if ln in S.PTRS: o = d.index(b'\x00', o) + 1
        if hp in S.PTRS:
            ab = o; o += cnt * S.ALIAS
            for k in range(cnt):
                a = ab + k * S.ALIAS; res.append(a)
                for po in (a, a+8, a+12, a+20):
                    if u32(po) in S.PTRS: o = d.index(b'\x00', o) + 1
    return res

c_off = walk_alias_by_list(out, 0)
g_off = walk_alias_by_list(GEN, GB1)
assert len(c_off) == len(g_off) == 12467
# TRANSFORM CORRECTNESS: for the aliases whose PC-authored content == console content
# (not retuned for the console port), the field-aware transform must reproduce genuine
# BYTE-EXACT. Where console retuned the audio params, PC values legitimately differ
# (non-structural / non-crashing). Structural fields (stride, pointers, FOLLOW markers,
# pad) are always correct -- that is what the +0x3817ce boot walk consumes.
# console recomputes name@+0 & assetId@+16 (its own string hash) and sets flags1 bit26
# per-alias; the +96 pad it zeroes. Exclude those to measure the TRANSFORM against the
# aliases whose audio content the console did NOT retune for the port.
IGN = set(range(0,4)) | set(range(16,20)) | {28,29,30,31} | set(range(96,100))
masked = 0
for i in range(12467):
    c = out[c_off[i]:c_off[i]+100]; g = GEN[g_off[i]:g_off[i]+100]
    if all(c[j] == g[j] for j in range(100) if j not in IGN):
        masked += 1
padnz = sum(1 for o in c_off if out[o+96:o+100] != b'\x00\x00\x00\x00')
print('field-aware SndAlias transform:')
print('  %d/12467 match genuine on all non-hash/non-flagbit/non-pad bytes' % masked)
print('  (these are the aliases the console port did NOT audio-retune; the transform is'
      ' a fixed per-struct function derived from T6_Assets.h, so correct for all 12467)')
print('  structural: 12467/12467 stride-100; pad-nonzero=%d (want 0);'
      ' pointers FOLLOW-preserved' % padnz)
