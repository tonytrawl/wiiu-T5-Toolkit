"""The sound name-hash is an additive polynomial h=h*P+c (last char weight 1, proven by
amb_air_l/amb_air_r differing by exactly the char delta). Solve P from equal-length names
differing in one interior position, then solve seed, then verify on all list ids."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref'))
import sndbank_probe as S
GEN = open(os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'), 'rb').read()
end0, _, _, _ = S.parse_sndbank(GEN, 0x45bea9e, '>'); GB1 = end0
M = 1 << 32

def walk(d, b):
    u32 = lambda o: struct.unpack_from('>I', d, o)[0]
    name_p, ac = struct.unpack_from('>2I', d, b)
    o = b + S.BODY; L=[]
    if name_p in S.PTRS: o = d.index(b'\x00', o) + 1
    base = o; o += ac * S.ALIASLIST
    for i in range(ac):
        lb = base + i*S.ALIASLIST
        ln, lid, hp, cnt, sq = struct.unpack_from('>5I', d, lb)
        if ln in S.PTRS:
            nul=d.index(b'\x00',o); L.append((d[o:nul],lid)); o=nul+1
        if hp in S.PTRS:
            o += cnt*S.ALIAS
            for k in range(cnt):
                a=(o- cnt*S.ALIAS)+k*S.ALIAS
                for po in (a,a+8,a+12,a+20):
                    if u32(po) in S.PTRS: o=d.index(b'\x00',o)+1
    return L
L = walk(GEN, GB1)
by = {s:h for s,h in L}

def egcd(a,b):
    if b==0: return (a,1,0)
    g,x,y=egcd(b,a%b); return (g,y,x-(a//b)*y)
def inv(a,m=M):
    a%=m; g,x,_=egcd(a,m); return x%m if g==1 else None

# find same-length pairs differing in exactly ONE position; record (posFromEnd, delta_char, delta_hash)
cands = {}
Ls = list(by.items())
for i in range(len(Ls)):
    s1,h1=Ls[i]
    for j in range(i+1,len(Ls)):
        s2,h2=Ls[j]
        if len(s1)!=len(s2): continue
        diff=[k for k in range(len(s1)) if s1[k]!=s2[k]]
        if len(diff)!=1: continue
        k=diff[0]; posFromEnd=len(s1)-1-k
        dc=(s1[k]-s2[k]); dh=(h1-h2)%M
        # dh = dc * P^posFromEnd  => P^posFromEnd = dh * inv(dc)
        di=inv(dc%M)
        if di is None: continue
        pe=(dh*di)%M
        cands.setdefault(posFromEnd,set()).add(pe)
# posFromEnd=1 gives P directly
print('posFromEnd candidate counts:', {k:len(v) for k in sorted(cands) for v in [cands[k]]})
Pset = cands.get(1,set())
print('P candidates (posFromEnd=1):', [hex(p) for p in list(Pset)[:10]])
# intersect with sqrt of posFromEnd=2 (P^2) to disambiguate
P=None
for p in Pset:
    if 2 in cands and (p*p)%M in cands[2]:
        P=p; break
if P is None and Pset:
    P=list(Pset)[0]
print('CHOSEN P=0x%08x (%d)'%(P,P) if P else 'no P')

if P:
    # solve seed from one pair: h = seed*P^n + sum(c_i * P^(n-1-i))
    def poly_noseed(s):
        h=0
        for c in s: h=(h*P + c)%M
        return h
    def Ppow(n):
        r=1
        for _ in range(n): r=(r*P)%M
        return r
    # h = seed*P^n + poly_noseed(s)  -> seed = (h - poly_noseed(s)) * inv(P^n)
    s0,h0=L[0]
    seed=((h0-poly_noseed(s0))*inv(Ppow(len(s0))))%M
    print('solved seed=0x%08x from %r'%(seed,s0))
    def full(s):
        h=seed
        for c in s: h=(h*P+c)%M
        return h
    hits=sum(1 for s,h in L if full(s)==h)
    print('VERIFY list-id: %d/%d match with P=0x%x seed=0x%x'%(hits,len(L),P,seed))
    # show a few
    for s,h in L[:5]:
        print('   %-16r target=0x%08x got=0x%08x %s'%(s.decode('latin-1'),h,full(s),'OK' if full(s)==h else 'X'))
