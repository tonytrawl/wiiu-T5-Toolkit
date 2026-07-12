"""Crack SndAlias.assetId = hash(assetFileName). Brute-force (normalization x hashfunc)."""
import struct, sys, os, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S
GEN = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
end0, _, _, _ = S.parse_sndbank(GEN, 0x45bea9e, '>'); GB1 = end0

def walk(d, b):
    u32 = lambda o: struct.unpack_from('>I', d, o)[0]
    name_p, ac, alias_p, ai, rc, rp, dc, dp = struct.unpack_from('>8I', d, b)
    o = b + S.BODY; pairs = []
    if name_p in S.PTRS: o = d.index(b'\x00', o) + 1
    base = o; o += ac * S.ALIASLIST
    for i in range(ac):
        lb = base + i * S.ALIASLIST
        ln, lid, hp, cnt, sq = struct.unpack_from('>5I', d, lb)
        if ln in S.PTRS: o = d.index(b'\x00', o) + 1
        if hp in S.PTRS:
            ab = o; o += cnt * S.ALIAS
            for k in range(cnt):
                a = ab + k * S.ALIAS; aid = u32(a+16); got = {}
                for tag, po in (('name', a), ('sub', a+8), ('sec', a+12), ('file', a+20)):
                    if u32(po) in S.PTRS:
                        nul = d.index(b'\x00', o); got[tag] = d[o:nul]; o = nul + 1
                if 'file' in got: pairs.append((got['file'], aid))
    return pairs
pairs = walk(GEN, GB1)
print('assetFileName/assetId pairs:', len(pairs))

# normalizations
def norms(s):
    b = s.decode('latin-1')
    outs = {}
    outs['raw'] = b
    x = b
    if x.lower().startswith('raw\\'): x = x[4:]
    outs['no_raw'] = x
    outs['no_raw_fwd'] = x.replace('\\', '/')
    # strip extension chain (.SL55.wiiu.snd etc -> up to first dot after last sep)
    base_ = x
    outs['no_raw_lower'] = x.lower()
    outs['no_raw_fwd_lower'] = x.replace('\\', '/').lower()
    # strip everything from first '.' in the final component
    sep = max(x.rfind('\\'), x.rfind('/'))
    comp = x[sep+1:]; head = x[:sep+1]
    noext = head + (comp.split('.')[0])
    outs['no_ext'] = noext
    outs['no_ext_lower'] = noext.lower()
    outs['no_ext_fwd_lower'] = noext.replace('\\', '/').lower()
    outs['raw_lower'] = b.lower()
    outs['raw_fwd_lower'] = b.replace('\\', '/').lower()
    return outs

def fnv1a(s, seed=2166136261, prime=16777619):
    h = seed
    for c in s.encode('latin-1','replace'): h = ((h ^ c) * prime) & 0xffffffff
    return h
def fnv1(s, seed=2166136261, prime=16777619):
    h = seed
    for c in s.encode('latin-1','replace'): h = ((h * prime) ^ c) & 0xffffffff
    return h
def djb2(s):
    h = 5381
    for c in s.encode('latin-1','replace'): h = ((h*33)+c) & 0xffffffff
    return h
def djb2x(s):
    h = 5381
    for c in s.encode('latin-1','replace'): h = ((h*33)^c) & 0xffffffff
    return h
def crc(s): return zlib.crc32(s.encode('latin-1','replace')) & 0xffffffff
def sdbm(s):
    h=0
    for c in s.encode('latin-1','replace'): h=(c+(h<<6)+(h<<16)-h)&0xffffffff
    return h
HFUN = {'fnv1a':fnv1a,'fnv1':fnv1,'djb2':djb2,'djb2x':djb2x,'crc':crc,'sdbm':sdbm}

normkeys = list(norms(pairs[0][0]).keys())
best = []
for nk in normkeys:
    for hn, hf in HFUN.items():
        hits = 0
        for s, aid in pairs[:400]:
            if hf(norms(s)[nk]) == aid: hits += 1
        if hits: best.append((hits, nk, hn))
best.sort(reverse=True)
print('MATCHES (hits/400):')
for h, nk, hn in best[:15]:
    print('  %-20s %-8s -> %d' % (nk, hn, h))
if not best:
    print('  none. sample target vs fnv1a variants for first pair:')
    s, aid = pairs[0]
    for nk in normkeys:
        print('   %-20s %-60r fnv1a=0x%08x  target=0x%08x' % (nk, norms(s)[nk][:58], fnv1a(norms(s)[nk]), aid))
