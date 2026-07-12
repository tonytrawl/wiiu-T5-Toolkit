#!/usr/bin/env python3
import sys, struct, zlib, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
import rpldis2 as R

RPL = r"E:\Wii U Black ops 2\code\t6mp_cafef_rpl.rpl"
data, secs = R.load(RPL)
by_addr, syms = R.build_syms(data, secs)

text = next(s for s in secs if s.name=='.text')
tbytes = R.sec_bytes(data, text)
tbase = text.addr
print(f".text base=0x{tbase:08x} decompressed size=0x{len(tbytes):x}")

md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)

def word_at(va):
    o = va - tbase
    return tbytes[o:o+4]

def disasm(va, count):
    o = va - tbase
    for insn in md.disasm(tbytes[o:o+count*4], va):
        print(f"  0x{insn.address:08x}: {word_at(insn.address).hex()}  {insn.mnemonic:8} {insn.op_str}")

print("\n== call site region 0x027DC708..0x027DC760 (hksL_loadfile_FastFile) ==")
disasm(0x027DC708, 24)

print("\n== call site word @0x027DC74C ==")
w = word_at(0x027DC74C)
print("  bytes:", w.hex())
# decode bl: 0x48000001 | (disp&0x03fffffc)
val = struct.unpack('>I', w)[0]
if (val & 0xfc000003) in (0x48000001,):  # bl
    disp = val & 0x03fffffc
    if disp & 0x02000000: disp -= 0x04000000
    tgt = 0x027DC74C + disp
    print(f"  -> bl target = 0x{tgt:08x}  (LUI_CoD_GetRawFile=0x02884ed0? {tgt==0x02884ed0})")

print("\n== LUI_CoD_FFReader @0x02884EA8 (reader field offsets) ==")
disasm(0x02884EA8, 10)

# ---- code cave scan: longest zero run in .text ----
print("\n== code cave scan (zero runs >= 0x40) ==")
runs=[]
i=0; n=len(tbytes)
while i < n:
    if tbytes[i]==0:
        j=i
        while j<n and tbytes[j]==0: j+=1
        if j-i >= 0x40:
            runs.append((tbase+i, j-i))
        i=j
    else:
        i+=1
for va,ln in runs:
    print(f"  cave VA=0x{va:08x} len=0x{ln:x} ({ln} bytes)")
if not runs:
    print("  NONE >= 0x40")

# also check .data / .bss writable slot candidates for RawFile scratch
print("\n== .data / .bss for scratch ==")
for s in secs:
    if s.name in ('.data','.bss'):
        print(f"  {s.name} addr=0x{s.addr:08x} size=0x{s.size:x} flags=0x{s.flags:08x}")
