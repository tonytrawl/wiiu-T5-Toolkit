import struct,pickle,time
t0=time.time()
M=pickle.load(open('_skate_simmap.pkl','rb'))
ae=M['assets_end']; spans=M['spans']
Z=open('mp_skate_authored.zone','rb').read()
p=r"C:/CemuFullDumps/Cemu.exe.2896.dmp"; f=open(p,'rb')
f.seek(8); ns,rva=struct.unpack('<II',f.read(8)); f.seek(rva); dr=f.read(ns*12); stt={}
for i in range(ns):
    t,s,l=struct.unpack_from('<III',dr,i*12); stt[t]=(s,l)
s,l=stt[9]; f.seek(l); nn,brva=struct.unpack('<QQ',f.read(16)); f.seek(l+16)
ranges=[]; off=brva
for i in range(nn):
    a,z=struct.unpack('<QQ',f.read(16)); ranges.append((a,z,off)); off+=z
sc=struct.unpack_from('>I',Z,40)[0]; o=64+sc*4
anc=Z[o+200:o+240]; anc_b5=(o+200)-64
# search all large ranges for the distinctive script-string anchor (guest base
# relocates every Cemu launch, so we can't filter by a hardcoded base)
ra=None
for (a,z,fo) in sorted(ranges,key=lambda t:-t[1]):
    if z<0x1000000: continue
    f.seek(fo); d=f.read(z); i=d.find(anc)
    if i>=0: ra,ri,rd=a,i,d; break
assert ra is not None, 'anchor not found in any range'
base=(ra+ri)-anc_b5; G=rd[base-ra:base-ra+0x6C00000]
print('zone window %.1fMB'%(len(G)/1e6),flush=True)
def needles(s,e):
    # yield (offset, 24B window) candidates across the whole body, distinctive first
    step=max(16,(e-s)//400)
    for cand in range(s,e-24,step):
        w=Z[cand:cand+24]
        if len(set(w))>=12 and w.count(0)<=10:
            yield cand,w
real={}; ok=miss=0; cursor=0; rate=0.011
order=sorted(spans,key=lambda t:t[3]); lastreal=None; laststream=None
for (idx,nm,root,s,e) in order:
    exp=cursor
    win_lo=max(0,exp-8192); win_hi=min(len(G),exp+400000+(e-s))
    hit=None
    tries=0
    for cand,nd in needles(s,e):
        tries+=1
        if tries>60: break
        j=G.find(nd,win_lo,win_hi)
        if j>=0 and G.find(nd,j+1,win_hi)<0:   # unique in window
            hit=j-(cand-s); break
    if hit is not None:
        real[s-64]=hit; ok+=1
        if lastreal is not None and (s-64)>laststream:
            rate=max(0.0,min(0.05,(hit-lastreal)/((s-64)-laststream)-1)) if False else rate
        lastreal=hit; laststream=s-64; cursor=hit+(e-s)
    else:
        miss+=1; cursor=exp+(e-s)+int((e-s)*rate)   # extrapolate a gap
print('measured %d/%d, %d missed  (%.0fs)'%(ok,ok+miss,miss,time.time()-t0),flush=True)
pickle.dump(dict(base=base,ae=ae,real=real),open('_skate_realmap.pkl','wb'))
print('saved',flush=True)
