import struct
DMP=r'C:/CemuFullDumps/Cemu.exe.40004.dmp'; BASE=0x000002444a8a0000
f=open(DMP,'rb'); f.seek(8); ns,rva=struct.unpack('<II',f.read(8)); f.seek(rva); dr=f.read(ns*12); stt={}
for i in range(ns):
    t,s,l=struct.unpack_from('<III',dr,i*12); stt[t]=(s,l)
s,l=stt[9]; f.seek(l); nn,brva=struct.unpack('<QQ',f.read(16)); f.seek(l+16)
ranges=[]; off=brva
for i in range(nn):
    a,z=struct.unpack('<QQ',f.read(16)); ranges.append((a,z,off)); off+=z
def rd(host,n):
    for (a,z,fo) in ranges:
        if a<=host<a+z:
            f.seek(fo+(host-a)); return f.read(min(n,a+z-host))
    return None
s,l=stt[6]; f.seek(l); struct.unpack('<II',f.read(8))
ec,ef,er,ea=struct.unpack('<IIQQ',f.read(24))
import capstone
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
START=0x245a7411f00
code=rd(START,ea-START+8)
for ins in md.disasm(code,START):
    m='  <==FAULT' if ins.address==ea else ''
    print('  %012x %-8s %s%s'%(ins.address,ins.mnemonic,ins.op_str,m))
