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
def deep_ascii(g,depth=2):
    # follow up to `depth` pointer hops to find an ascii string
    s=ascii_at(g)
    if s: return s
    if depth<=0: return None
    for off in range(0,24,4):
        v=be32(g+off)
        if v and 0x1000<v<0x50000000:
            r=deep_ascii(v,depth-1)
            if r: return '(+%d)->%s'%(off,r)
    return None
print('=== arrayA @0x10497558 : 2 entries x 24B, hunt for image/name ptrs ===')
A=0x10497558
for i in range(2):
    row=rdg(A+i*24,24)
    print(' [%d]'%i, row.hex())
    for off in range(0,24,4):
        v=struct.unpack_from('>I',row,off)[0]
        if 0x1000<v<0x50000000:
            s=deep_ascii(v,2)
            print('    +%2d ptr=0x%08x %s'%(off,v,('-> '+s) if s else ''))
print('=== struct @0x128dbaa0: scan 0..0x1200 for ptrs->ascii (deep) ===')
base=0x128dbaa0
for o in range(0,0x1200,4):
    v=be32(base+o)
    if v and 0x1000<v<0x50000000:
        s=deep_ascii(v,2)
        if s: print('  +0x%04x ptr=0x%08x -> %s'%(o,v,s))
print('=== +0x10c4 shader-name-ptr-array: list a few names ===')
p=be32(base+0x10c4)
print(' +0x10c4 ->0x%08x'%p)
for k in range(6):
    q=be32(p+k*4); s=ascii_at(q) if q else None
    print('   [%d]=0x%08x %s'%(k,q or 0, ('-> '+s) if s else ''))
