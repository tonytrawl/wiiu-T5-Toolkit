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
def le32(g):
    b=rdg(g,4); return struct.unpack('<I',b)[0] if b and len(b)==4 else None
def asciiat(g,maxn=64):
    b=rdg(g,maxn)
    if not b: return None
    z=b.find(b'\0')
    s=b[:z if z>=0 else maxn]
    if len(s)>=3 and all(32<=c<127 for c in s): return s.decode()
    return None
base=0x128dbaa0
print('=== struct @0x%x first 0x40 bytes (BE dwords), resolve ptrs to ascii ==='%base)
for o in range(0,0x40,4):
    v=be32(base+o)
    tag=''
    if v is not None:
        s=asciiat(v)
        if s: tag='-> "%s"'%s
    print('  +0x%02x = 0x%08x %s'%(o,v if v is not None else 0,tag))
print('=== scan +0x00..+0x1200 for any ptr resolving to ASCII (names) ===')
seen=set()
for o in range(0,0x1200,4):
    v=be32(base+o)
    if v and 0x1000<v<0x50000000:
        s=asciiat(v)
        if s and s not in seen and len(s)>4:
            seen.add(s); print('  +0x%04x -> "%s"'%(o,s))
