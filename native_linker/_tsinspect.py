import sys,struct,os,json
sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import techset_translate as TT
corpus=TT.load_corpus()
meta=corpus['mc_lit_sm_t0c0_90wz6fe2']
print('corpus meta:',{k:meta[k] for k in meta if k!='path'}, 'path=',meta['path'])
blob=open(os.path.join(TT.ROOT,meta['path']),'rb').read()
print('corpus blob len',len(blob))
def be32(d,o): return struct.unpack_from('>I',d,o)[0]
def be16(d,o): return struct.unpack_from('>H',d,o)[0]
FOLLOW=0xFFFFFFFF
# walk corpus blob: body 136, name@136, then techniques for each FOLLOW slot
slots=[be32(blob,8+i*4) for i in range(32)]
import shader_probe as SP
c=SP.Cur(blob,136); c.cstr(160)
tname_off={}
def walk_pass(t,label):
    pc=be16(blob,t+6)
    print('  technique @%d passCount=%d name?'%(t,pc))
    for i in range(pc):
        po=t+8+i*24
        vd,vs,ps=be32(blob,po),be32(blob,po+4),be32(blob,po+8)
        a12,a13,a14=blob[po+12],blob[po+13],blob[po+14]
        args_p=be32(blob,po+20)
        print('    pass%d po=%d cnt(12,13,14)=(%d,%d,%d) sum=%d args_p=%#x vd=%#x vs=%#x ps=%#x'%(
            i,po,a12,a13,a14,a12+a13+a14,args_p,vd,vs,ps))
# need proper technique offsets; reuse Extractor for correctness
import techset_extract as TE
print('--- via Extractor on corpus blob ---')
try:
    ex=TE.Extractor(blob)
    for nm,(bo,eo) in ex.techsets.items():
        print('techset',nm,'body',bo,eo)
except Exception as e:
    print('extractor err',e)
