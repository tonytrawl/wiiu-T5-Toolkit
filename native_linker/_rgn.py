import struct
DMP=r'C:/CemuFullDumps/Cemu.exe.40004.dmp'
f=open(DMP,'rb'); f.seek(8); ns,rva=struct.unpack('<II',f.read(8)); f.seek(rva); dr=f.read(ns*12); stt={}
for i in range(ns):
    t,s,l=struct.unpack_from('<III',dr,i*12); stt[t]=(s,l)
s,l=stt[9]; f.seek(l); nn,brva=struct.unpack('<QQ',f.read(16)); f.seek(l+16)
ranges=[]; off=brva
for i in range(nn):
    a,z=struct.unpack('<QQ',f.read(16)); ranges.append((a,z,off)); off+=z
rip=0x245a7412121
for (a,z,fo) in ranges:
    if a<=rip<a+z:
        print('faultRIP region: 0x%x .. 0x%x  size=0x%x (%d MB)'%(a,a+z,z,z//1048576))
# total memory
tot=sum(z for _,z,_ in ranges)
print('ranges:',len(ranges),'total mem=%d MB'%(tot//1048576))
# show ranges > 4MB
print('large ranges:')
for (a,z,fo) in ranges:
    if z>4*1048576: print('  0x%011x size 0x%x (%d MB)'%(a,z,z//1048576))
