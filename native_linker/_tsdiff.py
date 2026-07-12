import sys,struct,os
sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import techset_translate as TT, techset_extract as TE, shader_probe as SP
corpus=TT.load_corpus(); meta=corpus['mc_lit_sm_t0c0_90wz6fe2']
blob=open(os.path.join(TT.ROOT,meta['path']),'rb').read()
Z=open('mp_skate_measured.zone','rb').read()
def be32(d,o): return struct.unpack_from('>I',d,o)[0]
def be16(d,o): return struct.unpack_from('>H',d,o)[0]
FOLLOW=0xFFFFFFFF
name=b'mc_lit_sm_t0c0_90wz6fe2\x00'
# find occurrences in Z
offs=[]; i=Z.find(name)
while i>=0: offs.append(i); i=Z.find(name,i+1)
print('name string in measured.zone at:',[hex(o) for o in offs])
# corpus: name is at o+136 => body start 0. In measured, body start = nameoff-136
for no in offs:
    o=no-136
    print('== candidate techset body @0x%x (name@0x%x)'%(o,no))
    # sanity: worldVertFormat@+4, slots
    slots=[be32(Z,o+8+k*4) for k in range(32)]
    nf=sum(1 for v in slots if v==FOLLOW); nz=sum(1 for v in slots if v==0)
    print('   slots FOLLOW=%d zero=%d other=%d'%(nf,nz,32-nf-nz))
# Now compare the crash pass. In corpus, crash technique@74229 pass0 po=74237.
# Map by walking measured techset with same structure. Use relative offset from body start.
# corpus body start=0, so crash po_rel=74237. Emitted may differ if sizes changed, but exact-subst
# should be near-verbatim. Compare a window.
cpo=74237
print('CORPUS pass bytes @%d:'%cpo, blob[cpo:cpo+24].hex())
print('  counts(12,13,14)=',blob[cpo+12],blob[cpo+13],blob[cpo+14],'args_p=%#x'%be32(blob,cpo+20))
if offs:
    o=offs[0]-136
    mpo=o+cpo
    print('MEASURED pass bytes @0x%x:'%mpo, Z[mpo:mpo+24].hex())
    print('  counts(12,13,14)=',Z[mpo+12],Z[mpo+13],Z[mpo+14],'args_p=%#x'%be32(Z,mpo+20))
    # full-body byte diff over the techset extent
    L=len(blob)
    seg=Z[o:o+L]
    if len(seg)==L:
        diffs=[k for k in range(L) if seg[k]!=blob[k]]
        print('techset body byte-diffs vs corpus: %d / %d'%(len(diffs),L))
        # show first few diff offsets and their context (are they pointer words?)
        for k in diffs[:12]:
            print('   diff@%d corpus=%02x meas=%02x'%(k,blob[k],seg[k]))
