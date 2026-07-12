#!/usr/bin/env python3
"""Verify the field-aware transform reproduces genuine SndAlias bytes for the
aligned prefix (aliases 0..3), ignoring the two console-recomputed hash fields
(+0 name, +16 assetId) and the +96 pad."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S
exec(open('_derive_sndalias.py').read().split('gen_rec, gend = collect(GEN, gb1')[0])
_r0, gb1 = collect(GEN, GB0, '>')
gen_rec, gend = collect(GEN, gb1, '>')
pc_rec, pcend = collect(PC, PB0, '<')

def sw32(b): return b''.join(b[i:i+4][::-1] for i in range(0,len(b),4))
def sw16(b): return b''.join(b[i:i+2][::-1] for i in range(0,len(b),2))

def alias_fieldaware(p):
    return sw32(p[0:52]) + sw16(p[52:86]) + p[86:96] + b'\x00\x00\x00\x00'

# ignore-mask: bytes 0..3 (name hash), 16..19 (assetId hash), 96..99 (pad)
IGN = set(range(0,4)) | set(range(16,20)) | set(range(96,100))
ok = bad = 0
for n in range(4):
    g = GEN[gen_rec['ALIAS'][n]:gen_rec['ALIAS'][n]+100]
    p = PC[pc_rec['ALIAS'][n]:pc_rec['ALIAS'][n]+100]
    e = alias_fieldaware(p)
    diff = [i for i in range(100) if e[i] != g[i] and i not in IGN]
    print('alias %d: %s' % (n, 'MATCH' if not diff else 'DIFF at %s' % diff))
    for i in diff:
        print('   byte %d exp=%02x gen=%02x' % (i, e[i], g[i]))
