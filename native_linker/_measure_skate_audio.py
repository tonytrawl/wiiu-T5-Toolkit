"""Widened skate runtime re-measure targeting the AUDIO/tail region coverage.
Uses dump 34096 (field-aware measured build = furthest into gameplay -> most of the
tail laid out) and mp_skate_measured.zone (matches that dump's content). Widens the
needle window (bridge the multi-MB gfx/audio runtime bands), tries cap, and needle
looseness vs _measure_real.py (which got 51% off an early load-crash dump)."""
import struct, pickle, time
t0 = time.time()
M = pickle.load(open('_skate_simmap.pkl', 'rb'))
ae = M['assets_end']; spans = M['spans']
Z = open('mp_skate_measured.zone', 'rb').read()          # matches dump 34096
p = r"C:/CemuFullDumps/Cemu.exe.34096.dmp"; f = open(p, 'rb')
f.seek(8); ns, rva = struct.unpack('<II', f.read(8)); f.seek(rva); dr = f.read(ns*12); stt = {}
for i in range(ns):
    t, s, l = struct.unpack_from('<III', dr, i*12); stt[t] = (s, l)
s, l = stt[9]; f.seek(l); nn, brva = struct.unpack('<QQ', f.read(16)); f.seek(l+16)
ranges = []; off = brva
for i in range(nn):
    a, z = struct.unpack('<QQ', f.read(16)); ranges.append((a, z, off)); off += z
sc = struct.unpack_from('>I', Z, 40)[0]; o = 64 + sc*4
anc = Z[o+200:o+240]; anc_b5 = (o+200)-64
ra = None
for (a, z, fo) in sorted(ranges, key=lambda t: -t[1]):
    if z < 0x1000000: continue
    f.seek(fo); d = f.read(z); i = d.find(anc)
    if i >= 0: ra, ri, rd = a, i, d; break
assert ra is not None, 'anchor not found in any range'
base = (ra+ri)-anc_b5; G = rd[base-ra:base-ra+0x6C00000]
print('zone window %.1fMB' % (len(G)/1e6), flush=True)

def needles(s, e):
    step = max(16, (e-s)//1000)                          # WIDENED: more candidates
    for cand in range(s, e-24, step):
        w = Z[cand:cand+24]
        if len(set(w)) >= 10 and w.count(0) <= 12:       # LOOSENED distinctiveness
            yield cand, w

real = {}; ok = miss = 0; cursor = 0; rate = 0.011
order = sorted(spans, key=lambda t: t[3]); lastreal = None; laststream = None
audio_hits = 0
for (idx, nm, root, s, e) in order:
    exp = cursor
    win_lo = max(0, exp-8192); win_hi = min(len(G), exp + 4000000 + (e-s))  # WIDENED window
    hit = None; tries = 0
    for cand, nd in needles(s, e):
        tries += 1
        if tries > 250: break                            # WIDENED tries cap
        j = G.find(nd, win_lo, win_hi)
        if j >= 0 and G.find(nd, j+1, win_hi) < 0:        # unique in window
            hit = j-(cand-s); break
    if hit is not None:
        real[s-64] = hit; ok += 1
        lastreal = hit; laststream = s-64; cursor = hit+(e-s)
        if root in ('SndBank',):
            audio_hits += 1
            print('  MEASURED %-12s span[%d] simpos=%d -> realpos=%d (delta %+d)'
                  % (root, idx, s-64, hit, hit-(s-64)), flush=True)
    else:
        miss += 1; cursor = exp+(e-s)+int((e-s)*rate)
print('measured %d/%d, %d missed  SndBank-hits=%d  (%.0fs)'
      % (ok, ok+miss, miss, audio_hits, time.time()-t0), flush=True)
pickle.dump(dict(base=base, ae=ae, real=real), open('_skate_realmap_v2.pkl', 'wb'))
print('saved _skate_realmap_v2.pkl', flush=True)
