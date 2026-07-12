import sys
sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import produce_nobackbone as PN
PC=open('../mp_skate_pc.zone','rb').read()
spans,err=PN.walk_pc_bodies(PC)
print('spans:',len(spans),'err:',err)
needle=b'pimp_shader_vertcolorsimple'
offs=[]; i=PC.find(needle)
while i>=0: offs.append(i); i=PC.find(needle,i+1)
print('occurrences:',len(offs))
def owner(o):
    for e in spans:
        s,en=e[3],e[4]
        if s is not None and en is not None and s<=o<en: return e
    return None
for o in offs:
    e=owner(o)
    s=PC[o:o+48]; z=s.find(b'\0')
    lbl = '%s/%s idx%d [%d..%d]'%(e[1],e[2],e[0],e[3],e[4]) if e else '<stringtable/none>'
    print('  @0x%06x %-42s  %s'%(o, s[:z].decode('latin1'), lbl))
