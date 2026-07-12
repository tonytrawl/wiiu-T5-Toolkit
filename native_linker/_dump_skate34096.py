"""Skate bisect via dump: identify the struct the AX voice callback (+0x3817ce) walks.
Fault: mov eax,[rdi]; bswap; rbx=eax+base; mov ecx,[rbx+0x364] -> rdi's first BE word
= wild 0xb1c68f11. Dump the RDI struct + surroundings to identify which asset owns it."""
import struct

DMP = r"C:/CemuFullDumps/Cemu.exe.34096.dmp"
# skate crashlog RDI=0x000001a63ed69490 -> guest low32 0x3ed69490, base = RDI - guest
RDI_HOST = 0x000001a63ed69490
RDI_GUEST = RDI_HOST & 0xffffffff
BASE = RDI_HOST - RDI_GUEST
print('derived guest BASE=0x%x  RDI_guest=0x%x' % (BASE, RDI_GUEST))

f = open(DMP, 'rb')
f.seek(8); ns, rva = struct.unpack('<II', f.read(8))
f.seek(rva); dr = f.read(ns * 12); stt = {}
for i in range(ns):
    t, s, l = struct.unpack_from('<III', dr, i * 12); stt[t] = (s, l)
s, l = stt[9]
f.seek(l); nn, brva = struct.unpack('<QQ', f.read(16)); f.seek(l + 16)
ranges = []; off = brva
for i in range(nn):
    a, z = struct.unpack('<QQ', f.read(16)); ranges.append((a, z, off)); off += z

def read(host, n):
    for (a, z, fo) in ranges:
        if a <= host < a + z:
            f.seek(fo + (host - a)); return f.read(min(n, a + z - host))
    return None

def g(guest, n):
    return read(BASE + guest, n)

def hexd(b, base=0):
    out = []
    for i in range(0, len(b), 16):
        row = b[i:i+16]
        out.append('%08x  %-48s %s' % (base+i, ' '.join('%02x' % x for x in row),
                   ''.join(chr(x) if 32 <= x < 127 else '.' for x in row)))
    return '\n'.join(out)

print('\n== RDI struct @ guest 0x%x (AX callback walks this; +0=BE wild 0xb1c68f11) ==' % RDI_GUEST)
b = g(RDI_GUEST - 0x20, 0x120)
print(hexd(b, RDI_GUEST - 0x20) if b else '  NOT MAPPED')

# Which guest region is 0x3ed69490? Print a wider window scanning for ascii (alias names?)
print('\n== scan 0x600 bytes from RDI for ascii runs (sound alias names => SndBank) ==')
w = g(RDI_GUEST - 0x100, 0x600)
if w:
    run = b''
    for i, ch in enumerate(w):
        if 32 <= ch < 127:
            run += bytes([ch])
        else:
            if len(run) >= 5:
                print('  +0x%x: %r' % (RDI_GUEST - 0x100 + i - len(run), run))
            run = b''
