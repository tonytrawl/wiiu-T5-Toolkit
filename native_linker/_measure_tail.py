"""Map the GfxWorld-tail runtime divergence: pick distinctive ASCII-ish needles across
the zone tail [GfxWorld start .. end], find each UNIQUELY in a skate dump, record
(zone_b5, runtime_b5, delta). Reveals where the +1,252,389 -> +1,081,088 delta transitions
so we can anchor piecewise. String-like needles avoid the pointer-relocation problem."""
import struct, sys
DMP = sys.argv[1] if len(sys.argv) > 1 else r'C:/CemuFullDumps/Cemu.exe.39080.dmp'
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
base = (ra+ri)-anc_b5
print('anchor OK; scanning tail...')

GFX = 59696031
END = len(Z)
STEP = (END - GFX)//60
results = []
for zoff in range(GFX, END-24, STEP):
    # find an ascii-heavy 20-byte needle near zoff
    nd = None
    for c in range(zoff, min(zoff+STEP, END-20)):
        w = Z[c:c+20]
        printable = sum(1 for x in w if 32 <= x < 127)
        if printable >= 18 and len(set(w)) >= 10:
            nd = (c, w); break
    if nd is None:
        continue
    c, w = nd
    i = rd.find(w)
    if i >= 0 and rd.find(w, i+1) < 0:        # unique
        rt = (ra+i)-base
        results.append((c-64, rt, rt-(c-64)))
print('measured %d tail points:' % len(results))
prev = None
for zb5, rt, delta in results:
    mark = ''
    if prev is not None and abs(delta-prev) > 2000:
        mark = '  <-- DELTA STEP %+d' % (delta-prev)
    print('  zone_b5=%-9d runtime_b5=%-9d delta=%+d%s' % (zb5, rt, delta, mark))
    prev = delta
