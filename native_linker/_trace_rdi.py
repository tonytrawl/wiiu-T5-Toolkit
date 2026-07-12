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
s,l=stt[6]; f.seek(l); tid,al=struct.unpack('<II',f.read(8))
ec,ef,er,ea=struct.unpack('<IIQQ',f.read(24))
# disasm backward window
import capstone
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64); md.detail=True
START=ea-0x400
code=rd(START,0x420)
print("faultRIP=0x%x  window 0x%x..0x%x"%(ea,START,ea))
for ins in md.disasm(code,START):
    s=ins.op_str
    # flag anything touching rdi/edi or [rsp+0x74]
    hit=''
    if 'di' in s.split(',')[0][:5] if ',' in s else False: hit=' <-writes?'
    if 'rsp + 0x74' in s or 'rsp + 0x74]' in s: hit=' <-[rsp+0x74]'
    m='  <==FAULT' if ins.address==ea else ''
    interesting = ('edi' in s or 'rdi' in s or '0x74]' in s)
    if interesting or m:
        print('  %012x %-8s %s%s%s'%(ins.address,ins.mnemonic,s,hit,m))
