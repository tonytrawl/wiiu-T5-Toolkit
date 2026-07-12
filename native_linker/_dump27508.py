"""Analyze Cemu full dump 27508 (raid transplant crash): guest-memory corruption
of a thread TCB. Reuses the Memory64List parsing pattern from _measure_real.py."""
import struct, sys

DMP = r"C:/CemuFullDumps/Cemu.exe.27508.dmp"
BASE = 0x000002347d0b0000        # guest 0 -> host (from log: Init Wii U memory space base)
f = open(DMP, 'rb')
f.seek(8); ns, rva = struct.unpack('<II', f.read(8))
f.seek(rva); dr = f.read(ns * 12); stt = {}
for i in range(ns):
    t, s, l = struct.unpack_from('<III', dr, i * 12); stt[t] = (s, l)
s, l = stt[9]                    # Memory64ListStream
f.seek(l); nn, brva = struct.unpack('<QQ', f.read(16)); f.seek(l + 16)
ranges = []; off = brva
for i in range(nn):
    a, z = struct.unpack('<QQ', f.read(16)); ranges.append((a, z, off)); off += z
print('ranges:', nn, 'total %.2f GB' % (sum(z for _, z, _ in ranges) / 1e9))

def read(host, n):
    for (a, z, fo) in ranges:
        if a <= host < a + z:
            f.seek(fo + (host - a)); return f.read(min(n, a + z - host))
    return None

def g(guest, n):                 # read guest memory
    return read(BASE + guest, n)

def hexd(b, base=0):
    out = []
    for i in range(0, len(b), 16):
        row = b[i:i+16]
        out.append('%08x  %-48s %s' % (base+i, ' '.join('%02x' % x for x in row),
                   ''.join(chr(x) if 32 <= x < 127 else '.' for x in row)))
    return '\n'.join(out)

# sanity: guest base valid? read Main IP region as PPC (BE)
print('\n== Main thread IP 0x02240758 (guest code, BE) ==')
code = g(0x02240758 - 0x20, 0x60)
if code: print(hexd(code, 0x02240758 - 0x20))
else: print('  base wrong / not mapped -- will anchor-search')

print('\n== corrupted TCB @ guest 0x10e87450 (garbage Ent/IP/Pri) ==')
tcb = g(0x10e87450 - 0x40, 0x140)
print(hexd(tcb, 0x10e87450 - 0x40) if tcb else '  not mapped')

print('\n== healthy Main TCB @ guest 0x0e000700 (for comparison) ==')
h = g(0x0e000700 - 0x40, 0x140)
print(hexd(h, 0x0e000700 - 0x40) if h else '  not mapped')
