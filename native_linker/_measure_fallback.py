import struct,pickle,time
t0=time.time()
S=pickle.load(open('_skate_simmap.pkl','rb')); R=pickle.load(open('_skate_realmap.pkl','rb'))
ae=S['assets_end']; spans=S['spans']; real=dict(R['real']); base=R['base']
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
ra=None
for (a,z,fo) in sorted(ranges,key=lambda t:-t[1]):
    if z<0x1000000: continue
    f.seek(fo); d=f.read(z); i=d.find(anc)
    if i>=0: ra,ri,rd=a,i,d; break
assert ra is not None, 'anchor not found in any range'
base=(ra+ri)-anc_b5; G=rd[base-ra:base-ra+0x6C00000]   # index==runtime b5
before=len(real)
for (idx,nm,root,s,e) in spans:
    if (s-64) in real: continue
    step=max(16,(e-s)//600); got=False
    for cand in range(s,e-24,step):
        w=Z[cand:cand+24]
        if len(set(w))<12 or w.count(0)>10: continue
        j=G.find(w)
        if j>=0 and G.find(w,j+1)<0:
            real[s-64]=j-(cand-s); got=True; break
print('fallback added %d (total %d/%d)  (%.0fs)'%(len(real)-before,len(real),len(spans),time.time()-t0),flush=True)
# report critical
crit=('clipMap_t','GameWorldMp','MapEnts','SndBank','ComWorld','Glasses')
for (i,nm,root,s,e) in spans:
    if root in crit: print('  %-14s measured=%s'%(nm,(s-64) in real))
gfx=[(s,e) for (i,nm,r,s,e) in spans if r=='GfxWorld'][0]
post=[sp for sp in spans if sp[3]>=gfx[1]]
print('post-gfx measured %d/%d'%(sum(1 for sp in post if (sp[3]-64) in real),len(post)))
pickle.dump(dict(base=base,ae=ae,real=real),open('_skate_realmap.pkl','wb')); print('saved',flush=True)
