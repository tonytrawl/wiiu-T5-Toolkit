"""Reverse the console sound string-hash. The genuine raid bank stores real strings
(assetFileName, list names, subtitles) next to their hash fields (SndAlias.assetId@+16,
SndAliasList.id@+4). Extract (string,hash) pairs and brute-force candidate hash funcs."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S

GEN = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
end0, _, _, _ = S.parse_sndbank(GEN, 0x45bea9e, '>')
GB1 = end0
PTRS = S.PTRS

def walk_pairs(d, b):
    """Collect (string, hashfield) candidate pairs walking the bank BE."""
    u32 = lambda o: struct.unpack_from('>I', d, o)[0]
    name_p, ac, alias_p, ai, rc, rp, dc, dp = struct.unpack_from('>8I', d, b)
    o = b + S.BODY
    listname = []; assetfile = []; subs = []
    if name_p in PTRS: o = d.index(b'\x00', o) + 1
    base = o; o += ac * S.ALIASLIST
    for i in range(ac):
        lb = base + i * S.ALIASLIST
        lname_p, lid, head_p, cnt, seq = struct.unpack_from('>5I', d, lb)
        if lname_p in PTRS:
            nul = d.index(b'\x00', o); sstr = d[o:nul]; o = nul + 1
            listname.append((sstr, lid, lname_p))       # list name string, list id
        if head_p in PTRS:
            ab = o; o += cnt * S.ALIAS
            for k in range(cnt):
                a = ab + k * S.ALIAS
                nm, subp, secp, filep = (u32(a+0), u32(a+8), u32(a+12), u32(a+20))
                assetId = u32(a+16)
                # consume the 4 strings in order, capturing which
                got = {}
                for tag, po in (('name', a+0), ('sub', a+8), ('sec', a+12), ('file', a+20)):
                    if u32(po) in PTRS:
                        nul = d.index(b'\x00', o); got[tag] = d[o:nul]; o = nul + 1
                if 'file' in got:
                    assetfile.append((got['file'], assetId, nm))   # assetFileName, assetId, name-hash
                if 'sub' in got:
                    subs.append((got['sub'],))
    return listname, assetfile, subs

listname, assetfile, subs = walk_pairs(GEN, GB1)
print('pairs: listname=%d  assetfile=%d  subs=%d' % (len(listname), len(assetfile), len(subs)))
print('sample listname (string, id):')
for s, h, p in listname[:6]:
    print('   %-40r id=0x%08x  namep=0x%08x' % (s.decode('latin-1','replace'), h, p))
print('sample assetfile (string, assetId, name-hash):')
for s, aid, nm in assetfile[:6]:
    print('   %-46r assetId=0x%08x name=0x%08x' % (s.decode('latin-1','replace'), aid, nm))

# ---- candidate hash functions ----
def fnv1a(s, seed=2166136261):
    h = seed
    for c in s: h = ((h ^ c) * 16777619) & 0xffffffff
    return h
def fnv1(s, seed=2166136261):
    h = seed
    for c in s: h = ((h * 16777619) ^ c) & 0xffffffff
    return h
def djb2(s, seed=5381):
    h = seed
    for c in s: h = ((h * 33) + c) & 0xffffffff
    return h
def sdbm(s):
    h = 0
    for c in s: h = (c + (h << 6) + (h << 16) - h) & 0xffffffff
    return h
def crc32(s):
    import zlib; return zlib.crc32(s) & 0xffffffff
# CoD "Com_HashKey"/dvar style, and T6 SL string hash (fnv with tolower)
def fnv1a_lower(s, seed=2166136261):
    h = seed
    for c in s:
        if 65 <= c <= 90: c += 32
        h = ((h ^ c) * 16777619) & 0xffffffff
    return h
def fnv1a_lower_bslash(s, seed=2166136261):
    h = seed
    for c in s:
        if 65 <= c <= 90: c += 32
        if c == 47: c = 92
        h = ((h ^ c) * 16777619) & 0xffffffff
    return h

CANDS = [fnv1a, fnv1, djb2, sdbm, crc32, fnv1a_lower, fnv1a_lower_bslash]

def try_all(pairs, label):
    print('\n=== cracking %s (%d pairs) ===' % (label, len(pairs)))
    for fn in CANDS:
        hits = sum(1 for tup in pairs if fn(tup[0]) == tup[1])
        # also try masking to a4xxxxxx? just report raw
        if hits: print('  %-18s exact=%d/%d' % (fn.__name__, hits, len(pairs)))
    # show what fnv1a gives vs target for first pair
    if pairs:
        s, h = pairs[0][0], pairs[0][1]
        print('  first: %r target=0x%08x  fnv1a=0x%08x fnv1a_lower=0x%08x djb2=0x%08x'
              % (s, h, fnv1a(s), fnv1a_lower(s), djb2(s)))

try_all([(s, h) for s, h, p in listname], 'SndAliasList.id vs list-name')
try_all([(s, aid) for s, aid, nm in assetfile], 'SndAlias.assetId vs assetFileName')
