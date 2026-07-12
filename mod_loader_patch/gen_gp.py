#!/usr/bin/env python3
"""Generate a Cemu graphic-pack patches.txt from labeled PPC asm.
Assembles with keystone to validate + compute label offsets, then emits
Cemu 'codeCaveSize' style lines (addresses < cave = cave-relative), with
symbol defs for labels. Branches reference _labels; Cemu resolves them.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from keystone import Ks, KS_ARCH_PPC, KS_MODE_32, KS_MODE_BIG_ENDIAN

MODULE = 0x1F48D80A
CALLSITE = 0x0280E374

# (label, cemu_asm)  -- cemu_asm uses rN and _label refs (Cemu syntax == keystone-ish but keystone
# wants numeric regs & numeric branch targets). We keep two forms: 'cemu' for output, 'ks' for asm.
# Simplify: write with rN + _label; derive ks form by stripping 'r' and resolving branches to 0x0.
PROG = [
 ("_hook",  "mflr r0"),
 (None,     "stwu r1, -0x40(r1)"),
 (None,     "stw r0, 0x44(r1)"),
 (None,     "stw r31, 0x34(r1)"),
 (None,     "stw r30, 0x30(r1)"),
 (None,     "mr r31, r3"),
 # find end of name -> r6 at NUL
 (None,     "mr r6, r31"),
 ("_find",  "lbz r4, 0(r6)"),
 (None,     "cmpwi r4, 0"),
 (None,     "beq _fend"),
 (None,     "addi r6, r6, 1"),
 (None,     "b _find"),
 ("_fend",  "addi r6, r6, -9"),      # suffix start = end-9
 (None,     "cmpw r6, r31"),
 (None,     "blt _skip"),            # name shorter than 9 -> skip
 # build "lobby.lua" on stack @0x0C
 (None,     "lis r5, 0x6C6F"),
 (None,     "ori r5, r5, 0x6262"),
 (None,     "stw r5, 0x0C(r1)"),
 (None,     "lis r5, 0x792E"),
 (None,     "ori r5, r5, 0x6C75"),
 (None,     "stw r5, 0x10(r1)"),
 (None,     "lis r5, 0x6100"),
 (None,     "stw r5, 0x14(r1)"),
 (None,     "addi r7, r1, 0x0C"),
 (None,     "li r8, 9"),
 ("_cmp",   "lbz r4, 0(r6)"),
 (None,     "lbz r5, 0(r7)"),
 (None,     "cmpw r4, r5"),
 (None,     "bne _skip"),
 (None,     "addi r6, r6, 1"),
 (None,     "addi r7, r7, 1"),
 (None,     "addic. r8, r8, -1"),
 (None,     "bne _cmp"),
 # matched suffix -> FS_ReadFile(name,&buf), result ignored (detect-only)
 ("_dodisk","li r0, 0"),
 (None,     "stw r0, 8(r1)"),
 (None,     "mr r3, r31"),
 (None,     "addi r4, r1, 8"),
 (None,     "lis r12, 0x024F"),
 (None,     "ori r12, r12, 0xBA24"),
 (None,     "mtctr r12"),
 (None,     "bctrl"),
 # always return stock rawfile
 ("_skip",  "mr r3, r31"),
 (None,     "lis r12, 0x028B"),
 (None,     "ori r12, r12, 0xDF98"),
 (None,     "mtctr r12"),
 (None,     "bctrl"),
 (None,     "lwz r30, 0x30(r1)"),
 (None,     "lwz r31, 0x34(r1)"),
 (None,     "lwz r0, 0x44(r1)"),
 (None,     "addi r1, r1, 0x40"),
 (None,     "mtlr r0"),
 (None,     "blr"),
]

# compute offsets
labels={}
off=0
for lab,asm in PROG:
    if lab: labels[lab]=off
    off+=4
size=off
cave=0x100
assert size<=cave, size

# validate with keystone: replace _labels with numeric relative addr, rN->N
ks=Ks(KS_ARCH_PPC, KS_MODE_32|KS_MODE_BIG_ENDIAN)
off=0
for lab,asm in PROG:
    a=asm
    # branch target label -> absolute (keystone addr-based)
    m=re.search(r'_(\w+)', a)
    ksasm=re.sub(r'\br(\d+)\b', r'\1', a)  # rN -> N
    if m and ('_'+m.group(1)) in labels:
        tgt=labels['_'+m.group(1)]
        ksasm=re.sub(r'_\w+', hex(tgt), ksasm)
    try:
        ks.asm(ksasm, addr=off)
    except Exception as e:
        print("KS FAIL @0x%02x: %s  (%s)  %s"%(off,asm,ksasm,e)); sys.exit(1)
    off+=4

# emit patches.txt
out=[]
out.append("# BO2 raw-lua hook -- Cemu runtime patch (no repack). DETECT-ONLY, suffix gate 'lobby.lua'.")
out.append("# Fires FS_ReadFile (logs 'Open file') for any *lobby.lua; returns stock content. Discovery+proof.")
out.append("")
out.append("[BO2 Raw Lua Loader]")
out.append("moduleMatches = 0x%08X"%MODULE)
out.append("")
out.append("codeCaveSize = 0x%X"%cave)
out.append("")
for lab in labels:
    out.append("%-8s = 0x%08X"%(lab, labels[lab]))
out.append("")
out.append("0x%08X = bla _hook"%CALLSITE)
out.append("")
off=0
for lab,asm in PROG:
    out.append("0x%08X = %s"%(off, asm))
    off+=4
txt="\n".join(out)+"\n"
dst=r"C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\graphicPacks\BO2_RawLuaLoader\patches.txt"
open(dst,"w",newline="\n").write(txt)
print("validated %d instrs, size=0x%x, labels=%s"%(len(PROG),size,labels))
print("wrote",dst)
EOF = None
