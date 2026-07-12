"""Measure where the skate SndBank actually landed at runtime (via its STABLE name
strings, immune to pointer relocation) vs where the extrapolated rebake placed it.
A nonzero delta = the mis-placed audio tail (GfxWorld gfx_skip band wrong)."""
import struct, sys
DMP = sys.argv[1] if len(sys.argv) > 1 else r'C:/CemuFullDumps/Cemu.exe.19388.dmp'
Z = open('mp_skate_measured.zone', 'rb').read()
f = open(DMP, 'rb')
f.seek(8); ns, rva = struct.unpack('<II', f.read(8)); f.seek(rva); dr = f.read(ns*12); stt = {}
for i in range(ns):
    t, s, l = struct.unpack_from('<III', dr, i*12); stt[t] = (s, l)
s, l = stt[9]; f.seek(l); nn, brva = struct.unpack('<QQ', f.read(16)); f.seek(l+16)
ranges = []; off = brva
for i in range(nn):
    a, z = struct.unpack('<QQ', f.read(16)); ranges.append((a, z, off)); off += z
sc = struct.unpack_from('>I', Z, 40)[0]; o = 64 + sc*4
anc = Z[o+200:o+240]; anc_b5 = (o+200)-64
ra = rd = None
for (a, z, fo) in sorted(ranges, key=lambda t: -t[1]):
    if z < 0x1000000: continue
    f.seek(fo); d = f.read(z); i = d.find(anc)
    if i >= 0: ra, ri, rd = a, i, d; break
assert ra is not None, 'anchor not found'
base = (ra+ri)-anc_b5
print('anchor OK; zone base established in dump')

def findall(hay, ndl, cap=8):
    out = []; i = hay.find(ndl)
    while i >= 0 and len(out) < cap:
        out.append(i); i = hay.find(ndl, i+1)
    return out

for nm in [b'mpl_skate.all\x00', b'mpl_skate.english\x00']:
    zpos = Z.find(nm) - 64
    occ = findall(rd, nm)
    print('%-18s zone_b5=%d  occurrences=%d' % (nm.rstrip(b'\x00').decode(), zpos, len(occ)))
    for i in occ:
        rt = (ra+i) - base
        print('    runtime_b5=%d   delta=%+d' % (rt, rt - zpos))
print('--- reference ---')
print('GfxWorld stream start b5 = %d' % (59696031 - 64))
print('zone end b5              = %d' % (len(Z) - 64))
