#!/usr/bin/env python3
"""v2: NAME-GATED, DETECT-ONLY raw-lua hook for the live update-build MP RPL.
Only for names matching an exact allowlist (ffotdzm.lua / ffotdmp.lua) does the
hook call FS_ReadFile (proving disk read + logging an 'Open file' line); it then
returns the STOCK GetRawFile result regardless. Zero content risk, and no
streaming hang because non-matching lua never touch disk. Grows only .text.
"""
import sys, struct, zlib, binascii, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from keystone import Ks, KS_ARCH_PPC, KS_MODE_32, KS_MODE_BIG_ENDIAN
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

IN  = r"C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\mlc01\usr\title\0005000e\1010cf00\code\t6mp_cafef_rpl.rpl.prerawlua.bak"
OUT = r"C:\Users\Tony - Main Rig\Downloads\Testing enviroment\mod_loader_patch\out\t6mp_cafef_rpl.rpl"

GETRAW   = 0x028bdf98   # LUI_CoD_GetRawFile
FS_READ  = 0x024fba24   # FS_ReadFile(name, &buf)->size
CALLSITE = 0x0280e374   # bl GetRawFile in hksL_loadfile_FastFile
T1       = 0x1009b904   # rodata "ui_mp/t6/zombie/ffotdzm.lua"
T2       = 0x1009b93c   # rodata "ui_mp/t6/ffotdmp.lua"

def secs_of(d):
    shoff=struct.unpack(">I",d[0x20:0x24])[0]; n=struct.unpack(">H",d[0x30:0x32])[0]
    return shoff,n,[list(struct.unpack(">IIIIIIIIII",d[shoff+i*40:shoff+i*40+40])) for i in range(n)]
def dec_sec(d,sh):
    fl,sz,off=sh[2],sh[5],sh[4]; raw=d[off:off+sz]
    return bytearray(zlib.decompress(bytes(raw[4:]))) if (fl&0x08000000 and sz) else bytearray(raw)
def sec_name(d,S,shstrndx,i):
    tab=dec_sec(d,S[shstrndx]); o=S[i][0]; e=tab.find(b'\0',o); return tab[o:e].decode('latin1')

def hi(x): return (x>>16)&0xffff
def lo(x): return x&0xffff

def build():
    d=bytearray(open(IN,'rb').read())
    shoff,N,S=secs_of(d); shstrndx=struct.unpack(">H",d[0x32:0x34])[0]
    names={i:sec_name(d,S,shstrndx,i) for i in range(N)}
    TEXT=next(i for i in range(N) if names[i]=='.text')
    CRCS=next(i for i in range(N) if S[i][1]==0x80000003)
    tdec=dec_sec(d,S[TEXT]); taddr=S[TEXT][3]
    while len(tdec)%4: tdec.append(0)
    cave_off=len(tdec); cave_va=taddr+cave_off

    asm=f"""
        mflr 0
        stwu 1,-0x20(1)
        stw 0,0x24(1)
        stw 31,0x1c(1)
        stw 30,0x18(1)
        mr 31,3
        mr 30,31
        lis 6,{hi(T1)} ; ori 6,6,{lo(T1)}
    cmp1:
        lbz 4,0(30) ; lbz 5,0(6)
        cmplw 4,5 ; bne next1
        cmpwi 4,0 ; beq dodisk
        addi 30,30,1 ; addi 6,6,1 ; b cmp1
    next1:
        mr 30,31
        lis 6,{hi(T2)} ; ori 6,6,{lo(T2)}
    cmp2:
        lbz 4,0(30) ; lbz 5,0(6)
        cmplw 4,5 ; bne skip
        cmpwi 4,0 ; beq dodisk
        addi 30,30,1 ; addi 6,6,1 ; b cmp2
    dodisk:
        li 0,0 ; stw 0,8(1)
        mr 3,31 ; addi 4,1,8
        lis 12,{hi(FS_READ)} ; ori 12,12,{lo(FS_READ)}
        mtctr 12 ; bctrl
    skip:
        mr 3,31
        lis 12,{hi(GETRAW)} ; ori 12,12,{lo(GETRAW)}
        mtctr 12 ; bctrl
        lwz 30,0x18(1)
        lwz 31,0x1c(1)
        lwz 0,0x24(1)
        addi 1,1,0x20
        mtlr 0
        blr
    """
    ks=Ks(KS_ARCH_PPC,KS_MODE_32|KS_MODE_BIG_ENDIAN)
    code,_=ks.asm(asm,addr=cave_va); hook=bytes(code)
    assert len(hook)%4==0
    tdec+=hook

    po=CALLSITE-taddr
    old=struct.unpack(">I",tdec[po:po+4])[0]
    disp=(cave_va-CALLSITE)&0x03FFFFFC
    struct.pack_into(">I",tdec,po,0x48000001|disp)

    newtext=struct.pack(">I",len(tdec))+zlib.compress(bytes(tdec),9)
    tcrc=binascii.crc32(bytes(tdec))&0xffffffff
    move_from=S[TEXT][4]
    prefix=bytearray(d[:move_from])
    struct.pack_into(">I",prefix,S[CRCS][4]+TEXT*4,tcrc)
    out=bytearray(prefix)
    order=sorted((i for i in range(N) if S[i][4]>=move_from and S[i][5]>0),key=lambda i:S[i][4])
    for i in order:
        while len(out)%0x40: out.append(0)
        no=len(out)
        payload=newtext if i==TEXT else bytes(d[S[i][4]:S[i][4]+S[i][5]])
        out+=payload
        struct.pack_into(">I",out,shoff+i*40+16,no)
        struct.pack_into(">I",out,shoff+i*40+20,len(payload))
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    open(OUT,'wb').write(out)

    # verify
    p=open(OUT,'rb').read(); _,_,PS=secs_of(p)
    ptdec=zlib.decompress(p[PS[TEXT][4]:PS[TEXT][4]+PS[TEXT][5]][4:])
    md=Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN)
    ci=next(md.disasm(ptdec[po:po+4],CALLSITE))
    print(f"call site 0x{CALLSITE:08x}: {old:#010x} -> {ci.mnemonic} {ci.op_str}")
    print(f"cave_va=0x{cave_va:08x}  hook={len(hook)} bytes  gate T1=0x{T1:x} T2=0x{T2:x}")
    print(f"text crc=0x{tcrc:08x}  in {len(d)} -> out {len(out)}")
    print("=== hook ===")
    for ins in md.disasm(ptdec[cave_off:cave_off+len(hook)],cave_va):
        print(f"  0x{ins.address:08x}: {ins.mnemonic:8} {ins.op_str}")
    print("wrote",OUT)

if __name__=='__main__': build()
