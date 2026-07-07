import struct,sys; sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import struct_layout, walker as W, pc_to_console as P2C
CO=open('../wiiu_ref/mp_raid_genuine.zone','rb').read(); PC=open('../PC ff/mp_raid.zone','rb').read()
Lc=struct_layout.Layout(W.HDR,console=True); Lp=struct_layout.Layout(W.HDR,console=False)
VEC=P2C.VEC_TYPES
BLO,BHI,HLO,HHI=P2C.BLOCK5_LO,P2C.BLOCK5_HI,P2C.HIALIAS_LO,P2C.HIALIAS_HI

def swap_mapped(cname, pname, poff, buf, boff, fixups, depth=0):
    cs=Lc.get(cname); ps=Lp.get(pname)
    pf={f.get('name'):f for f in ps['fields'] if 'error' not in f}
    for cf in cs['fields']:
        if 'error' in cf: continue
        nm=cf.get('name'); p=pf.get(nm)
        if p is None:  # console field with no PC counterpart -> zero (rare)
            continue
        co=boff+cf['offset']; po=poff+p['offset']
        base=cf['base']; arr=max(cf['arr'],1)
        if cf.get('is_ptr'):
            for k in range(arr):
                v=struct.unpack_from('<I',PC,po+k*4)[0]
                if BLO<=v<=BHI: struct.pack_into('>I',buf,co+k*4,v); fixups.append((co+k*4,(v-1)&0x1FFFFFFF))
                elif HLO<=v<HHI: struct.pack_into('>I',buf,co+k*4,(v+0x10000000)&0xffffffff)
                else: struct.pack_into('>I',buf,co+k*4,v)
            continue
        if base in VEC:
            for w in range(cf['size']//4):
                struct.pack_into('>I',buf,co+w*4,struct.unpack_from('<I',PC,po+w*4)[0])
            continue
        if base in Lc.structs:
            esz_c=Lc._resolve(base)[0]; esz_p=Lp._resolve(base)[0]
            for k in range(arr):
                swap_mapped(base,base,po+k*esz_p,buf,co+k*esz_c,fixups,depth+1)
            continue
        esz=cf['size']//arr
        for k in range(arr):
            o=k*esz
            if esz==1: buf[co+o]=PC[po+o]
            elif esz==2: struct.pack_into('>H',buf,co+o,struct.unpack_from('<H',PC,po+o)[0])
            elif esz==8: struct.pack_into('>Q',buf,co+o,struct.unpack_from('<Q',PC,po+o)[0])
            elif esz%4==0:
                for w in range(esz//4): struct.pack_into('>I',buf,co+o+w*4,struct.unpack_from('<I',PC,po+o+w*4)[0])

cgw=0x2b7029d; pgw=0x3f34930
size=Lc.get('GfxWorld')['size']
buf=bytearray(size); fx=[]
swap_mapped('GfxWorld','GfxWorld',pgw,buf,0,fx)
gen=CO[cgw:cgw+size]
# compare, classifying diffs: pointer-field bytes (fixups) vs scalar
fxpos=set()
for co,_ in fx:
    fxpos.update(range(co,co+4))
scalar_diffs=[j for j in range(size) if buf[j]!=gen[j] and j not in fxpos]
ptr_diffs=[j for j in range(size) if buf[j]!=gen[j] and j in fxpos]
print('GfxWorld BODY mapped-convert: size=%d'%size)
print('  pointer-field diff bytes (need omap, expected): %d'%len(ptr_diffs))
print('  SCALAR/float diff bytes (must be 0 if conversion correct): %d'%len(scalar_diffs))
if scalar_diffs:
    runs=[]
    for j in scalar_diffs:
        if runs and j==runs[-1][1]+1: runs[-1][1]=j
        else: runs.append([j,j])
    for a,b in runs[:15]: print('    scalar diff [%d..%d] conv=%s gen=%s'%(a,b,buf[a:b+1][:8].hex(),gen[a:b+1][:8].hex()))
