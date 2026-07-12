#!/usr/bin/env python3
import sys, struct, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
import rpldis2 as R

RPL = sys.argv[1]
# live update-build VAs (resolved from .symtab)
GETRAW   = 0x028bdf98
LOADFILE = 0x0280e330
LOADFILE_SZ = 0x1b4
READER   = 0x028bdeec
FS_READ  = 0x024fba24

data, secs = R.load(RPL)
text = next(s for s in secs if s.name=='.text')
tbytes = R.sec_bytes(data, text)
tbase = text.addr
print(f".text base=0x{tbase:08x} decomp size=0x{len(tbytes):x}")
md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
def w(va): o=va-tbase; return tbytes[o:o+4]
def dis(va,cnt):
    o=va-tbase
    for i in md.disasm(tbytes[o:o+cnt*4], va):
        print(f"  0x{i.address:08x}: {w(i.address).hex()}  {i.mnemonic:8} {i.op_str}")

print("\n== hksL_loadfile_FastFile body, find bl GetRawFile ==")
callsite=None
o=LOADFILE-tbase
for ins in md.disasm(tbytes[o:o+LOADFILE_SZ], LOADFILE):
    val=struct.unpack('>I', w(ins.address))[0]
    tgt=None
    if (val & 0xfc000003)==0x48000001:
        disp=val&0x03fffffc
        if disp&0x02000000: disp-=0x04000000
        tgt=ins.address+disp
    mark=''
    if tgt==GETRAW:
        callsite=ins.address; mark='  <==== CALL SITE (bl GetRawFile)'
    print(f"  0x{ins.address:08x}: {w(ins.address).hex()}  {ins.mnemonic:8} {ins.op_str}{mark}")
print(f"\n  CALL SITE = 0x{callsite:08x}" if callsite else "  CALL SITE NOT FOUND")

print("\n== LUI_CoD_FFReader (reader field offsets) ==")
dis(READER, 16)

print("\n== code cave scan (zero runs >= 0x40 in .text) ==")
runs=[]; i=0; n=len(tbytes)
while i<n:
    if tbytes[i]==0:
        j=i
        while j<n and tbytes[j]==0: j+=1
        if j-i>=0x40: runs.append((tbase+i,j-i))
        i=j
    else: i+=1
for va,ln in runs: print(f"  cave VA=0x{va:08x} len=0x{ln:x}")
if not runs: print("  NONE >= 0x40 -> must grow .text")
print(f"\n  .text uncompressed end VA = 0x{tbase+len(tbytes):08x}  (append-cave location)")
for s in secs:
    if s.name in ('.data','.bss','.syscall'):
        print(f"  {s.name} addr=0x{s.addr:08x} size=0x{s.size:x}")
