#!/usr/bin/env python3
import struct, zlib, binascii, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
IN  = r"C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\mlc01\usr\title\0005000e\1010cf00\code\t6mp_cafef_rpl.rpl"
OUT = r"C:\Users\Tony - Main Rig\Downloads\Testing enviroment\mod_loader_patch\out\t6mp_cafef_rpl.rpl"
def secs(d):
    shoff=struct.unpack(">I",d[0x20:0x24])[0]; n=struct.unpack(">H",d[0x30:0x32])[0]
    return shoff,n,[list(struct.unpack(">IIIIIIIIII",d[shoff+i*40:shoff+i*40+40])) for i in range(n)]
for tag,path in (("IN",IN),("OUT",OUT)):
    d=open(path,'rb').read(); shoff,n,S=secs(d)
    TEXT=next(i for i in range(n) if S[i][3]==0x02000000 and S[i][1]==1)
    DATA=next(i for i in range(n) if S[i][3]==0x1012af80)
    CRCS=next(i for i in range(n) if S[i][1]==0x80000003)
    move_from=min(S[TEXT][4],S[DATA][4])
    print(f"[{tag}] file={len(d)}  CRCS off=0x{S[CRCS][4]:x} entsize={S[CRCS][9]} (in prefix? {S[CRCS][4]<move_from})")
    for i in (TEXT,DATA):
        raw=d[S[i][4]:S[i][4]+S[i][5]]
        dec=zlib.decompress(raw[4:]); usize=struct.unpack('>I',raw[:4])[0]
        crc=binascii.crc32(dec)&0xffffffff
        stored=struct.unpack(">I", d[S[CRCS][4]+i*4:S[CRCS][4]+i*4+4])[0]
        nm='.text' if i==TEXT else '.data'
        print(f"   {nm}: off=0x{S[i][4]:x} csize={S[i][5]} usize={usize} declen={len(dec)} crc=0x{crc:08x} stored=0x{stored:08x} {'OK' if crc==stored else 'MISMATCH'}")
    # overlap check on OUT: all section [off,off+size) non-overlapping & within file
    if tag=="OUT":
        segs=sorted((S[i][4],S[i][5],i) for i in range(n) if S[i][5]>0 and S[i][1]!=8)
        prev=0; ok=True
        for off,sz,i in segs:
            if off<prev: print(f"   OVERLAP at sec {i} off=0x{off:x} < prev 0x{prev:x}"); ok=False
            if off+sz>len(d): print(f"   OOB sec {i}"); ok=False
            prev=off+sz
        print("   layout:", "OK non-overlapping, in-bounds" if ok else "BROKEN")
