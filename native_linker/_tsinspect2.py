import sys,struct,os
sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import techset_translate as TT, techset_extract as TE, shader_probe as SP
corpus=TT.load_corpus(); meta=corpus['mc_lit_sm_t0c0_90wz6fe2']
blob=open(os.path.join(TT.ROOT,meta['path']),'rb').read()
def be32(d,o): return struct.unpack_from('>I',d,o)[0]
def be16(d,o): return struct.unpack_from('>H',d,o)[0]
FOLLOW=0xFFFFFFFF
ex=TE.Extractor(blob)
# tech_offs are technique body file offsets
print('tech_offs:',ex.tech_offs[:5],'...total',len(ex.tech_offs))
# For each technique, walk passes; for each pass with args_p==FOLLOW, capture arg counts
# and try to resolve ps shader name to detect the crash pass.
def cstr(d,o):
    z=d.find(b'\0',o); return d[o:z]
hits=[]
for t in ex.tech_offs:
    pc=be16(blob,t+6)
    c=SP.Cur(blob,t+8+pc*24)
    for i in range(pc):
        po=t+8+i*24
        vd,vs,ps=be32(blob,po),be32(blob,po+4),be32(blob,po+8)
        a=(blob[po+12],blob[po+13],blob[po+14]); args_p=be32(blob,po+20)
        # advance cursor through inline objs to find shader names
        # we just record counts; separately search for shader name proximity
        if 8 in a or args_p==FOLLOW:
            hits.append((t,i,po,a,args_p))
from collections import Counter
cc=Counter(h[3] for h in hits)
print('arg-count tuples (all passes):')
for k,v in sorted(cc.items()): print('  ',k,'x',v)
print('total passes captured:',len(hits))
# find passes whose arg counts sum includes 8 in one slot
eights=[h for h in hits if 8 in h[3]]
print('passes with a count==8 in a group:',len(eights), eights[:5])
