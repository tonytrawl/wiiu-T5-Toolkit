#!/usr/bin/env python3
"""Build the raw-.lua-from-disk patched MP RPL for the LIVE update build.
Grows .text (append hook cave) and .data (append 12B RawFile scratch),
repoints the bl at the GetRawFile call site to the cave, fixes section
offsets and the SHT_RPL_CRCS table. Writes to C: staging.
"""
import sys, struct, zlib, binascii, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from keystone import Ks, KS_ARCH_PPC, KS_MODE_32, KS_MODE_BIG_ENDIAN
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

IN  = r"C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\mlc01\usr\title\0005000e\1010cf00\code\t6mp_cafef_rpl.rpl"
OUT = r"C:\Users\Tony - Main Rig\Downloads\Testing enviroment\mod_loader_patch\out\t6mp_cafef_rpl.rpl"

# --- live update-build VAs (resolved from .symtab, verified by disasm) ---
GETRAW    = 0x028bdf98   # LUI_CoD_GetRawFile
FS_READ   = 0x024fba24   # FS_ReadFile(r3=name, r4=&buf) -> size
CALLSITE  = 0x0280e374   # bl GetRawFile inside hksL_loadfile_FastFile

def secs_of(d):
    shoff = struct.unpack(">I", d[0x20:0x24])[0]
    n = struct.unpack(">H", d[0x30:0x32])[0]
    S=[list(struct.unpack(">IIIIIIIIII", d[shoff+i*40:shoff+i*40+40])) for i in range(n)]
    return shoff, n, S
# sh fields: [0]name [1]type [2]flags [3]addr [4]off [5]size [6]link [7]info [8]align [9]entsize

def dec_sec(d, sh):
    fl,sz,off = sh[2],sh[5],sh[4]
    raw = d[off:off+sz]
    if fl & 0x08000000 and sz:
        return bytearray(zlib.decompress(bytes(raw[4:])))
    return bytearray(raw)

def sec_name(d, S, shstrndx, i):
    sh = S[shstrndx]
    tab = dec_sec(d, sh)
    o = S[i][0]; e = tab.find(b'\0', o); return tab[o:e].decode('latin1')

def build():
    d = bytearray(open(IN,'rb').read())
    shoff, N, S = secs_of(d)
    shstrndx = struct.unpack(">H", d[0x32:0x34])[0]
    names = {i: sec_name(d,S,shstrndx,i) for i in range(N)}
    TEXT = next(i for i in range(N) if names[i]=='.text')
    DATA = next(i for i in range(N) if names[i]=='.data')
    CRCS = next(i for i in range(N) if S[i][1]==0x80000003)

    tdec = dec_sec(d, S[TEXT]); taddr=S[TEXT][3]
    ddec = dec_sec(d, S[DATA]); daddr=S[DATA][3]

    # --- scratch: append 16 bytes to .data, 8-aligned slot ---
    while len(ddec) % 8: ddec.append(0)
    scratch_off = len(ddec)
    scratch_va  = daddr + scratch_off
    ddec += b'\x00'*16

    # --- cave: append hook to .text, 4-aligned ---
    while len(tdec) % 4: tdec.append(0)
    cave_off = len(tdec)
    cave_va  = taddr + cave_off

    # --- assemble hook for these VAs ---
    asm = f"""
        mflr   0
        stwu   1, -0x20(1)
        stw    0, 0x24(1)
        stw    31, 0x1c(1)
        mr     31, 3
        li     0, 0
        stw    0, 8(1)
        addi   4, 1, 8
        lis    12, {(FS_READ>>16)&0xffff}
        ori    12, 12, {FS_READ&0xffff}
        mtctr  12
        bctrl
        cmpwi  3, 0
        ble    miss
        lwz    4, 8(1)
        cmpwi  4, 0
        beq    miss
        lis    5, {(scratch_va>>16)&0xffff}
        ori    5, 5, {scratch_va&0xffff}
        stw    31, 0(5)
        stw    3, 4(5)
        stw    4, 8(5)
        mr     3, 5
        b      out
    miss:
        mr     3, 31
        lis    12, {(GETRAW>>16)&0xffff}
        ori    12, 12, {GETRAW&0xffff}
        mtctr  12
        bctrl
    out:
        lwz    31, 0x1c(1)
        lwz    0, 0x24(1)
        addi   1, 1, 0x20
        mtlr   0
        blr
    """
    ks = Ks(KS_ARCH_PPC, KS_MODE_32 | KS_MODE_BIG_ENDIAN)
    code, _ = ks.asm(asm, addr=cave_va)
    hook = bytes(code)
    assert len(hook)%4==0
    tdec[cave_off:cave_off] = b''   # noop
    tdec += hook

    # --- patch call site: bl CALLSITE -> cave ---
    po = CALLSITE - taddr
    old = struct.unpack(">I", tdec[po:po+4])[0]
    disp = (cave_va - CALLSITE) & 0x03FFFFFC
    struct.pack_into(">I", tdec, po, 0x48000001 | disp)  # bl (LK=1)

    # --- recompress + CRCs ---
    newtext = struct.pack(">I", len(tdec)) + zlib.compress(bytes(tdec), 9)
    newdata = struct.pack(">I", len(ddec)) + zlib.compress(bytes(ddec), 9)
    tcrc = binascii.crc32(bytes(tdec)) & 0xffffffff
    dcrc = binascii.crc32(bytes(ddec)) & 0xffffffff

    # rebuild file: keep everything before first-moved section; relayout all
    # sections whose file offset >= min(text,data) offset, in offset order.
    move_from = min(S[TEXT][4], S[DATA][4])
    prefix = bytearray(d[:move_from])
    # update CRC table entries (entsize per section = 4 bytes, indexed by section)
    crc_off = S[CRCS][4]
    struct.pack_into(">I", prefix, crc_off + TEXT*4, tcrc)
    struct.pack_into(">I", prefix, crc_off + DATA*4, dcrc)

    out = bytearray(prefix)
    order = sorted((i for i in range(N) if S[i][4] >= move_from and S[i][5] > 0),
                   key=lambda i: S[i][4])
    for i in order:
        while len(out) % 0x40: out.append(0)
        no = len(out)
        if i == TEXT:   payload = newtext
        elif i == DATA: payload = newdata
        else:           payload = bytes(d[S[i][4]:S[i][4]+S[i][5]])
        out += payload
        struct.pack_into(">I", out, shoff + i*40 + 16, no)            # sh_offset
        struct.pack_into(">I", out, shoff + i*40 + 20, len(payload))  # sh_size

    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT,'wb').write(out)

    # verify
    p = open(OUT,'rb').read()
    _,_,PS = secs_of(p)
    ptdec = zlib.decompress(p[PS[TEXT][4]:PS[TEXT][4]+PS[TEXT][5]][4:])
    md = Cs(CS_ARCH_PPC, CS_MODE_32|CS_MODE_BIG_ENDIAN)
    cs_ins = next(md.disasm(ptdec[po:po+4], CALLSITE))
    print(f"call site 0x{CALLSITE:08x}: {old:#010x} -> {cs_ins.mnemonic} {cs_ins.op_str}")
    print(f"cave_va     = 0x{cave_va:08x}  hook={len(hook)} bytes")
    print(f"scratch_va  = 0x{scratch_va:08x}  (.data +16)")
    print(f"text crc    = 0x{tcrc:08x}   data crc = 0x{dcrc:08x}")
    print(f"in size {len(d)} -> out size {len(out)}")
    print("=== hook disasm from file ===")
    ch = ptdec[cave_off:cave_off+len(hook)]
    for ins in md.disasm(ch, cave_va):
        print(f"  0x{ins.address:08x}: {ins.mnemonic:8} {ins.op_str}")
    print("wrote", OUT)

if __name__ == '__main__':
    build()
