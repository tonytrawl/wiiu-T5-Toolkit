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
        if a<=host<a+z:
            f.seek(fo+(host-a)); return f.read(min(n,a+z-host))
    return None
def be32(g): 
    b=rdg(g,4); return struct.unpack('>I',b)[0] if b else None
for name,base in [('rsi=0x128dbaa0',0x128dbaa0),('sibling=0x128dcba0',0x128dcba0)]:
    print('==',name)
    print('  +0x00 count =',be32(base))
    for off in (0x90,0x94,0x98,0x9c,0xa0):
        print('  +0x%x = 0x%08x'%(off,be32(base+off)))
    # shader name at +0x10c4
    p=be32(base+0x10c4)
    print('  +0x10c4 ptr = 0x%08x'%p, end=' ')
    if p:
        nm=rdg(p,48)
        z=nm.find(b'\0'); print('->',nm[:z if z>=0 else 48])
    else: print()
