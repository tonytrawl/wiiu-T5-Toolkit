#!/usr/bin/env python3
"""Capstone PPC32-BE disassembler / symbol resolver for T6 Wii U RPL.
Parses ELF sections, zlib-inflates sh_flags&0x08000000 sections (4-byte
uncompressed-size prefix), builds addr<->symbol from .symtab/.strtab.
"""
import sys, struct, zlib, io

RPL = sys.argv[1] if len(sys.argv) > 1 else r"E:\Wii U Black ops 2\code\t6mp_cafef_rpl.rpl"

class Sec:
    pass

def load(path):
    data = open(path, 'rb').read()
    assert data[:4] == b'\x7fELF', "not ELF"
    ei_class = data[4]  # 1=32
    ei_data  = data[5]  # 2=BE
    assert ei_class == 1 and ei_data == 2
    e_shoff  = struct.unpack('>I', data[0x20:0x24])[0]
    e_shentsize = struct.unpack('>H', data[0x2E:0x30])[0]
    e_shnum  = struct.unpack('>H', data[0x30:0x32])[0]
    e_shstrndx = struct.unpack('>H', data[0x32:0x34])[0]
    secs = []
    for i in range(e_shnum):
        off = e_shoff + i*e_shentsize
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_addralign, sh_entsize = \
            struct.unpack('>IIIIIIIIII', data[off:off+40])
        s = Sec()
        s.name_off=sh_name; s.type=sh_type; s.flags=sh_flags; s.addr=sh_addr
        s.offset=sh_offset; s.size=sh_size; s.link=sh_link; s.info=sh_info
        s.entsize=sh_entsize; s.idx=i
        secs.append(s)
    # section header string table
    shstr = secs[e_shstrndx]
    shstrtab = data[shstr.offset:shstr.offset+shstr.size]
    if shstr.flags & 0x08000000:
        usize = struct.unpack('>I', shstrtab[:4])[0]
        shstrtab = zlib.decompress(shstrtab[4:])
    def cstr(tab, o):
        e = tab.find(b'\0', o); return tab[o:e].decode('latin1')
    for s in secs:
        s.name = cstr(shstrtab, s.name_off)
    return data, secs

def sec_bytes(data, s):
    raw = data[s.offset:s.offset+s.size]
    if s.flags & 0x08000000:  # RPL zlib-compressed
        usize = struct.unpack('>I', raw[:4])[0]
        dec = zlib.decompress(raw[4:])
        assert len(dec) == usize, (len(dec), usize)
        return dec
    return raw

def build_syms(data, secs):
    symtab = next((s for s in secs if s.name=='.symtab'), None)
    strtab = next((s for s in secs if s.name=='.strtab'), None)
    if not symtab: return {}, []
    sb = sec_bytes(data, symtab)
    st = sec_bytes(data, strtab)
    def cstr(o):
        e = st.find(b'\0', o); return st[o:e].decode('latin1')
    n = len(sb)//16
    by_addr={}; syms=[]
    for i in range(n):
        nm, val, size, info, other, shndx = struct.unpack('>IIIBBH', sb[i*16:i*16+16])
        name = cstr(nm)
        syms.append((name, val, size))
        if name and val:
            by_addr.setdefault(val, name)
    return by_addr, syms

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    data, secs = load(RPL)
    print("== sections ==")
    for s in secs:
        print(f"  [{s.idx:2}] {s.name:20} type={s.type} flags=0x{s.flags:08x} addr=0x{s.addr:08x} off=0x{s.offset:x} size=0x{s.size:x}")
    by_addr, syms = build_syms(data, secs)
    print(f"\n== {len(syms)} symbols ==")
    targets = ['LUI_CoD_GetRawFile','hksL_loadfile_FastFile','LUI_CoD_FFReader',
               'FS_ReadFile','DB_FindXAssetHeader','hksL_loadfile','Sys_DefaultInstallPath']
    lut = {name:(val,size) for name,val,size in syms}
    for t in targets:
        hits = [(name,val,size) for name,val,size in syms if t.lower() in name.lower()]
        for name,val,size in hits:
            print(f"  {name:40} VA=0x{val:08x} size=0x{size:x}")
        if not hits:
            print(f"  {t:40} -- NOT FOUND")
