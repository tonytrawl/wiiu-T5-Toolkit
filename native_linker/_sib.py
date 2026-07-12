import struct
DMP=r'C:/CemuFullDumps/Cemu.exe.40004.dmp'; BASE=0x000002444a8a0000
f=open(DMP,'rb'); f.seek(8); ns,rva=struct.unpack('<II',f.read(8)); f.seek(rva); dr=f.read(ns*12); stt={}
for i in range(ns):
    t,s,l=struct.unpack_from('<III',dr,i*12); stt[t]=(s,l)
s,l=stt[9]; f.seek(l); nn,brva=struct.unpack('<QQ',f.read(16)); f.seek(l+16)
ranges=[]; off=brva
for i in range(nn):
    a,z=struct.unpack('<QQ',f.read(16)); ranges.append((a,z,off)); off+=z
def rdg(g,n):
    host=BASE+g
    for (a,z,fo) in ranges:
        if a<=host<a+z: f.seek(fo+(host-a)); return f.read(min(n,a+z-host))
    return None
def be32(g):
    b=rdg(g,4); return struct.unpack('>I',b)[0] if b and len(b)==4 else None
def ascii_at(g,mx=80):
    b=rdg(g,mx)
    if not b: return None
    z=b.find(b'\0'); s=b[:z if z>=0 else mx]
    return s.decode('latin1') if len(s)>=4 and all(32<=c<127 for c in s) else None
# the list at rbx=0x4e61fe90 — read a window as BE32 ptrs, find records w/ non-null +0x98
rbx=0x4e61fe90
print('=== list window @rbx=0x%x ==='%rbx)
recs=[]
for k in range(-8,16):
    v=be32(rbx+k*4)
    tag=''
    if v and 0x1000000<v<0x50000000:
        c=be32(v); p98=be32(v+0x98); p90=be32(v+0x90)
        if c is not None and c<2000:
            tag='rec? cnt=%s +0x90=0x%08x +0x98=0x%08x'%(c,p90 or 0,p98 or 0)
            recs.append(v)
    print('  [rbx%+d]=0x%08x %s'%(k*4,v or 0,tag))
# for the crash rec, dump arrayB target region even though base is null: can't.
# Instead: inspect the PRESENT arrayA of crash rec (0x10497558) entry @+8 -> is it a shader name?
print('=== crash rec arrayA entries: value@+8 as ptr->ascii? ===')
A=0x10497558
for i in range(2):
    v8=be32(A+i*24+8)
    print('  [%d] +8=0x%08x %s'%(i,v8 or 0, ('-> '+ascii_at(v8)) if v8 and ascii_at(v8) else ''))
# find any record with non-null +0x98 and dump its arrayB[0] entry, value@+8 -> ascii
print('=== scan nearby records for non-null +0x98, inspect arrayB[0] +8 ===')
seen=0
for base in recs:
    p98=be32(base+0x98)
    if p98 and 0x1000000<p98<0x50000000:
        e8=be32(p98+8); s=ascii_at(e8) if e8 else None
        print('  rec 0x%08x +0x98=0x%08x  arrayB[0]+8=0x%08x %s'%(base,p98,e8 or 0,('-> '+s) if s else ''))
        seen+=1
        if seen>4: break
if not seen: print('  (no sibling with non-null +0x98 in window)')
