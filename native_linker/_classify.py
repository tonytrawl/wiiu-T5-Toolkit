import sys, struct
sys.path.insert(0,'.'); sys.path.insert(0,'../../wiiu_ref'); sys.path.insert(0,'../wiiu_ref')
import produce_nobackbone as PN
PCP='../mp_skate_pc.zone'
PC=open(PCP,'rb').read()
spans=PN.walk_pc_bodies(PC)   # list of (start,end,root,...)?
print('walk_pc_bodies returned %d entries; sample:'%len(spans))
print(spans[0])
# find all occurrences of shader in PC
needle=b'pimp_shader_vertcolorsimple'
offs=[]; i=PC.find(needle)
while i>=0: offs.append(i); i=PC.find(needle,i+1)
print('shader string occurrences in PC:',len(offs))
def owner(o):
    for e in spans:
        s,en=e[0],e[1]
        if s<=o<en: return e
    return None
from collections import Counter
c=Counter()
for o in offs[:200]:
    e=owner(o)
    if e: c[e[2]]+=1
    else: c['<none/stringtable>']+=1
print('owner root histogram:',dict(c))
