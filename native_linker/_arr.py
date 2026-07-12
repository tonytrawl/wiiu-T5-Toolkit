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
base=0x128dbaa0
# dump raw bytes at +0x80..+0xb0 to see the ptr/count layout
b=rdg(base+0x80,0x40)
print('raw +0x80:',' '.join('%02x'%x for x in b))
# arrayA @ +0x90 = 0x10497558 ; dump first few 24B entries
A=0x10497558
d=rdg(A,0x18*4)
print('arrayA @0x%x (0x18 stride):'%A)
for i in range(4):
    row=d[i*0x18:(i+1)*0x18]
    print('  [%d]'%i,' '.join('%02x'%x for x in row))
# is 0x128dbaa0 within a mapped range? show which range
host=BASE+base
for (a,z,fo) in ranges:
    if a<=host<a+z:
        print('rsi range: host 0x%x..0x%x (guest 0x%x..0x%x) size 0x%x'%(a,a+z,a-BASE,a+z-BASE,z))
