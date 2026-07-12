import struct,glob,capstone
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
def sig(DMP):
    f=open(DMP,'rb'); f.seek(8); ns,rva=struct.unpack('<II',f.read(8)); f.seek(rva); dr=f.read(ns*12); stt={}
    for i in range(ns):
        t,s,l=struct.unpack_from('<III',dr,i*12); stt[t]=(s,l)
    s,l=stt[9]; f.seek(l); nn,brva=struct.unpack('<QQ',f.read(16)); f.seek(l+16)
    ranges=[]; off=brva
    for i in range(nn):
        a,z=struct.unpack('<QQ',f.read(16)); ranges.append((a,z,off)); off+=z
    def rd(host,n):
        for (a,z,fo) in ranges:
            if a<=host<a+z: f.seek(fo+(host-a)); return f.read(min(n,a+z-host))
        return None
    s,l=stt[6]; f.seek(l); struct.unpack('<II',f.read(8))
    ec,ef,er,ea=struct.unpack('<IIQQ',f.read(24))
    npar,_=struct.unpack('<II',f.read(8)); pars=struct.unpack('<15Q',f.read(120))
    code=rd(ea-0x10,0x30); ins_str='?'
    if code:
        for ins in md.disasm(code,ea-0x10):
            if ins.address==ea: ins_str='%s %s'%(ins.mnemonic,ins.op_str); break
    return ea,pars[1],ins_str
for D in sorted(glob.glob('C:/CemuFullDumps/Cemu.exe.3*.dmp')+glob.glob('C:/CemuFullDumps/Cemu.exe.40004.dmp')):
    try:
        ea,acc,ins=sig(D)
        print('%-40s faultRIP=%#x acc=%#x  FAULT: %s'%(D.split('/')[-1],ea,acc,ins))
    except Exception as e:
        print(D.split('/')[-1],'ERR',e)
