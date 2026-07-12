import sys,struct,os
sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import techset_translate as TT, techset_extract as TE, shader_probe as SP
corpus=TT.load_corpus(); meta=corpus['mc_lit_sm_t0c0_90wz6fe2']
blob=open(os.path.join(TT.ROOT,meta['path']),'rb').read()
def be16(o): return struct.unpack_from('>H',blob,o)[0]
def be32(o): return struct.unpack_from('>I',blob,o)[0]
FOLLOW=0xFFFFFFFF
t=74229; i=0; po=t+8+i*24
pc=be16(t+6)
print('technique@%d passCount=%d ; crash pass po=%d'%(t,pc,po))
a12,a13,a14=blob[po+12],blob[po+13],blob[po+14]
print('arg group counts (perPrim,perObj,stable?) = (%d,%d,%d) sum=%d'%(a12,a13,a14,a12+a13+a14))
print('bytes po+12..+24:',blob[po+12:po+24].hex())
# walk to args inline data. cursor starts after the pass-array of this technique, then per pass
# inline: vs (if FOLLOW), vd, ps, args. Need to replay ordering for pass 0.
c=SP.Cur(blob, t+8+pc*24)
def dump_args(nargs, base):
    print('  --- %d args at file off %d ---'%(nargs,base))
    lits=0
    from collections import Counter
    types=Counter()
    for j in range(nargs):
        atype=be16(base+j*8); up=be32(base+j*8+4); u1=be16(base+j*8+2)
        types[atype]+=1
        kind={1:'LIT_VS',4:'LIT_PS',7:'LIT_PS7',2:'SAMPLER?',3:'CODE?',0:'CODE0'}.get(atype,'t%d'%atype)
        note=''
        if up in (FOLLOW,) : note='(FOLLOW->inline float4)'
        elif up==0: note='(0)'
        else: note='(dest/idx=0x%x)'%up
        print('    arg%d type=%d(%s) dest@2=0x%x u@4=0x%x %s'%(j,atype,kind,u1,up,note))
        if up==FOLLOW and atype in (1,4): lits+=1
    print('  type histogram:',dict(types),'lits(inline float4)=',lits)
    return nargs*8+lits*16
# replay technique 74229 passes to reach pass0 args
for pi in range(pc):
    ppo=t+8+pi*24
    vd,vs,ps=be32(ppo),be32(ppo+4),be32(ppo+8)
    args_p=be32(ppo+20); nargs=blob[ppo+12]+blob[ppo+13]+blob[ppo+14]
    if vs==FOLLOW: SP.parse_shader_ref(c,'vs')
    if vd==FOLLOW: c.skip(SP.VD_SIZE)
    if ps==FOLLOW: SP.parse_shader_ref(c,'ps')
    if args_p==FOLLOW:
        base=c.o
        if pi==0:
            adv=dump_args(nargs,base)
            break
        # skip
        lits=0
        for j in range(nargs):
            atype=be16(base+j*8); up=be32(base+j*8+4)
            if up==FOLLOW and atype in (1,4): lits+=1
        c.skip(nargs*8+lits*16)
