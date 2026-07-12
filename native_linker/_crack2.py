"""Wider hash sweep against SndAliasList.id (short names) and SndAlias.assetId."""
import struct, sys, os, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S
GEN = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
end0, _, _, _ = S.parse_sndbank(GEN, 0x45bea9e, '>'); GB1 = end0

def walk(d, b):
    u32 = lambda o: struct.unpack_from('>I', d, o)[0]
    name_p, ac, alias_p, ai, rc, rp, dc, dp = struct.unpack_from('>8I', d, b)
    o = b + S.BODY; L=[]; A=[]
    if name_p in S.PTRS: o = d.index(b'\x00', o) + 1
    base = o; o += ac * S.ALIASLIST
    for i in range(ac):
        lb = base + i * S.ALIASLIST
        ln, lid, hp, cnt, sq = struct.unpack_from('>5I', d, lb)
        if ln in S.PTRS:
            nul=d.index(b'\x00',o); L.append((d[o:nul],lid)); o=nul+1
        if hp in S.PTRS:
            ab=o; o+=cnt*S.ALIAS
            for k in range(cnt):
                a=ab+k*S.ALIAS; aid=u32(a+16)
                for tag,po in (('name',a),('sub',a+8),('sec',a+12),('file',a+20)):
                    if u32(po) in S.PTRS:
                        nul=d.index(b'\x00',o);
                        if tag=='file': A.append((d[o:nul],aid))
                        o=nul+1
    return L,A
L,A = walk(GEN,GB1)
print('list-id pairs=%d  assetId pairs=%d'%(len(L),len(A)))

def jenkins(b,seed=0):
    h=seed
    for c in b:
        h=(h+c)&0xffffffff; h=(h+(h<<10))&0xffffffff; h^=(h>>6)
    h=(h+(h<<3))&0xffffffff; h^=(h>>11); h=(h+(h<<15))&0xffffffff
    return h&0xffffffff
def murmur2(b,seed=0):
    m=0x5bd1e995; r=24; l=len(b); h=(seed^l)&0xffffffff; i=0
    while l>=4:
        k=struct.unpack_from('<I',b,i)[0]
        k=(k*m)&0xffffffff; k^=k>>r; k=(k*m)&0xffffffff
        h=(h*m)&0xffffffff; h^=k; i+=4; l-=4
    if l==3: h^=b[i+2]<<16
    if l>=2: h^=b[i+1]<<8
    if l>=1: h^=b[i]; h=(h*m)&0xffffffff
    h^=h>>13; h=(h*m)&0xffffffff; h^=h>>15
    return h&0xffffffff
def murmur3(b,seed=0):
    c1=0xcc9e2d51;c2=0x1b873593;h=seed;l=len(b);i=0
    while l>=4:
        k=struct.unpack_from('<I',b,i)[0]
        k=(k*c1)&0xffffffff;k=((k<<15)|(k>>17))&0xffffffff;k=(k*c2)&0xffffffff
        h^=k;h=((h<<13)|(h>>19))&0xffffffff;h=(h*5+0xe6546b64)&0xffffffff;i+=4;l-=4
    k=0
    if l==3:k^=b[i+2]<<16
    if l>=2:k^=b[i+1]<<8
    if l>=1:
        k^=b[i];k=(k*c1)&0xffffffff;k=((k<<15)|(k>>17))&0xffffffff;k=(k*c2)&0xffffffff;h^=k
    h^=len(b);h^=h>>16;h=(h*0x85ebca6b)&0xffffffff;h^=h>>13;h=(h*0xc2b2ae35)&0xffffffff;h^=h>>16
    return h&0xffffffff
def fnv1a(b,seed=2166136261,p=16777619):
    h=seed
    for c in b: h=((h^c)*p)&0xffffffff
    return h
def fnv1(b,seed=2166136261,p=16777619):
    h=seed
    for c in b: h=((h*p)^c)&0xffffffff
    return h
def djb2(b):
    h=5381
    for c in b: h=((h*33)+c)&0xffffffff
    return h

FUN={'jenkins':jenkins,'murmur2':murmur2,'murmur3':murmur3,'fnv1a':fnv1a,'fnv1':fnv1,'djb2':djb2}
def variants(s):
    out={'raw':s,'lower':s.lower(),'null':s+b'\x00','lower_null':s.lower()+b'\x00'}
    return out

def sweep(pairs,label):
    print('\n== %s (%d) =='%(label,len(pairs)))
    found=False
    for vk in ['raw','lower','null','lower_null']:
        for fn_seed in [None]:
            for hn,hf in FUN.items():
                for seed in ([0,0xffffffff,2166136261,5381] if hn in('jenkins','murmur2','murmur3','fnv1a','fnv1') else [0]):
                    try:
                        if hn in ('jenkins','murmur2','murmur3','fnv1a','fnv1'):
                            hits=sum(1 for s,h in pairs[:300] if hf(variants(s)[vk],seed)==h)
                        else:
                            hits=sum(1 for s,h in pairs[:300] if hf(variants(s)[vk])==h)
                    except TypeError:
                        hits=sum(1 for s,h in pairs[:300] if hf(variants(s)[vk])==h)
                    if hits: print('  %-10s %-10s seed=0x%x -> %d/300'%(vk,hn,seed,hits)); found=True
    if not found: print('  no matches')

sweep(L,'SndAliasList.id')
sweep(A,'SndAlias.assetId')
# also: is list-id maybe == a masked/added value? show diffs between consecutive amb_ ids
print('\nfirst 8 list ids:', [hex(h) for _,h in L[:8]])
