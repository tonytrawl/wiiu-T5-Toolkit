#!/usr/bin/env python3
"""
DIAGNOSTIC (Path A, step 1) -- ISOLATED side project. Base linker READ-ONLY.

Tests the leading hypothesis for the additive-relink crash (fx_pistol_shell):
"a VERBATIM asset holds an alias pointer into a shared-data INTERIOR that the
conservative omap relink MISSES, so it goes stale after the +delta tail shift."

Method (no probe edits): monkeypatch the module-level `u32` of the four
instrumentable probes (xmodel/shader/fx/gfximage -- which cover XModel and its
inline Material/MaterialTechniqueSet/GfxImage, the crash type and the richest
interior-pointer types) to RECORD every absolute offset whose read value is an
ALIAS (0xA0000001..0xBFFFFFFF). Run each verbatim asset through its delimiter/probe
to harvest the TRUE pointer-field offsets, then classify each alias target:
  - registered  : target block-5 offset is a region the ReEmitter register()s
                  -> remap_ptr_omap RESOLVES it (safe today)
  - unregistered: target is NOT a registered start -> omap MISSES it; if the
                  target is >= shift_from it goes STALE after +delta == the bug.

Run from native_linker/:
  python "../dlc loading/native/fullrelink/diag_interior_ptrs.py" \
      "../dlc loading/native/upd_patch_mp.ff" --tag mp
"""
import sys, os, struct, argparse
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))   # Testing enviroment
for _p in (os.path.join(_ROOT, 'native_linker'), os.path.join(_ROOT, 'wiiu_ref'),
           os.path.join(_ROOT, 'WiiU_FF_Studio'), os.path.join(_ROOT, 'dlc loading', 'native')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_ORIG_CWD = os.getcwd()
os.chdir(os.path.join(_ROOT, 'native_linker'))

import wiiu_ff, wiiu_zone, struct_layout
import walker as W
import zone_stream as zs
import body_relayout as BR
import xmodel_probe, shader_probe, fx_probe, gfximage_probe

B5_BASE = 64
ALIAS_LO, ALIAS_HI = 0xA0000001, 0xBFFFFFFF

# ---- instrumentation: record alias-valued u32 reads across the 4 probes -------
_REC = []          # list of absolute offsets read as an alias
_RECORDING = False

def _make_recorder(orig):
    def u32(d, o):
        v = orig(d, o)
        if _RECORDING and ALIAS_LO <= v <= ALIAS_HI:
            _REC.append(o)
        return v
    return u32

_STRREC = []       # absolute offsets where an interior inline string BEGINS

def _wrap_cstr(cls):
    orig = cls.cstr
    if getattr(orig, '_wrapped', False):
        return
    def cstr(self, *a, **k):
        if _RECORDING:
            _STRREC.append(self.o)
        return orig(self, *a, **k)
    cstr._wrapped = True
    cls.cstr = cstr

def install_recorders():
    for m in (xmodel_probe, shader_probe, fx_probe, gfximage_probe):
        if not getattr(m.u32, '_wrapped', False):
            w = _make_recorder(m.u32); w._wrapped = True
            m.u32 = w
    for m in (xmodel_probe, shader_probe):
        if hasattr(m, 'Cur'):
            _wrap_cstr(m.Cur)
    # xmodel_probe also references shader_probe.u32 via `import shader_probe`,
    # and its own module-global u32 -- both patched above. gfximage kept for
    # completeness (some Material image paths route through it).

def load_zone(path):
    if not os.path.isabs(path):
        path = os.path.join(_ORIG_CWD, path)
    _h, zone, _n = wiiu_ff.decrypt(open(path, 'rb').read())
    return zone


def full_base_pass(zone, r):
    """Base ReEmitter pass over the ORIGINAL zone. Returns (registered_set, starts)
    where registered_set = every block-5 offset the emitter register()s (the domain
    remap_ptr_omap can resolve) and starts = [(start_file_off, root, nm)]."""
    L = struct_layout.Layout(W.HDR, console=True)
    zc = W.ZoneCode(W.ZC_DIR)
    w = zs.ZoneWriter(); w.push_block(zs.BLOCK_VIRTUAL)
    w.block_size[zs.BLOCK_VIRTUAL] = r.assets_end - B5_BASE
    em = BR.ReEmitter(zone, L, zc, w)
    starts = []
    cur = r.assets_end
    for (cid, pc, nm) in r.assets:
        root = W.ASSET_ROOT.get(nm)
        if root is None or root not in L.structs:
            continue
        starts.append((cur, root, nm))
        try:
            cur = em.emit_asset(root, cur)
        except Exception:
            break
    registered = set(em.omap.keys())          # block-5 offsets
    reached = starts[-1][0] if starts else 0
    print('   base pass: emitted through %d assets, last start @%d, src cursor stopped @%d/%d'
          % (len(starts), reached, cur, len(zone)))
    return registered, starts


# delimiter types we can harvest with the 4 instrumentable probes
PROBE_DELIM = {
    'XModel':               lambda z, o: xmodel_probe.parse_xmodel(z, o)[0],
    'MaterialTechniqueSet': lambda z, o: shader_probe.parse_techset(z, o)[0],
    'FxEffectDef':          lambda z, o: fx_probe.parse_fx(z, o)[0],
    'Material':             lambda z, o: (lambda c: (xmodel_probe.consume_material(z, c), c.o)[1])(xmodel_probe.Cur(z, o)),
    'GfxImage':             lambda z, o: (lambda c: (xmodel_probe.consume_image(z, c), c.o)[1])(xmodel_probe.Cur(z, o)),
    'GfxLightDef':          BR._lightdef_end,   # uses XP.consume_image internally (instrumented)
}


def main():
    global _RECORDING
    ap = argparse.ArgumentParser()
    ap.add_argument('zone_ff')
    ap.add_argument('--tag', default='mp')
    a = ap.parse_args()

    install_recorders()
    zone = load_zone(a.zone_ff)
    r = wiiu_zone.ZoneReader(zone); r.read_string_table(); r.read_asset_list()
    print('== %s : %d B, %d assets' % (os.path.basename(a.zone_ff), len(zone), r.asset_count))

    registered, starts = full_base_pass(zone, r)
    print('   registered block-5 offsets: %d' % len(registered))

    # shift_from = end of mapstable body (block-5 offset). Locate mapstable header
    # with patch_relink's validated finder (requires np==FOLLOW and values==FOLLOW).
    import patch_relink as PR
    needle = ('%s/mapstable.csv' % a.tag).encode()
    chdr, cols, rows = PR._st_header(zone, needle, le=False)
    name_end = zone.index(b'\x00', chdr + 20); cells0 = name_end + 1
    n = cols * rows; o = cells0 + n * 8
    for k in range(n):
        p, _h = struct.unpack_from('>2I', zone, cells0 + k*8)
        if p == 0xFFFFFFFF:
            o = zone.index(b'\x00', o) + 1
    con_body_end = o + n * 2
    shift_from = con_body_end - B5_BASE
    print('   mapstable body @%d..%d ; shift_from(block5)=%d' % (chdr, con_body_end, shift_from))

    # PASS 1: harvest every verbatim asset -> per-asset pointer offsets + a GLOBAL
    # registry of interior inline-string block-5 offsets (alias-able name targets
    # that emit_verbatim never registers).
    global _RECORDING
    harvest = []              # (start, root, nm, ptr_offsets)
    interior_str = set()      # block-5 offsets of interior inline strings
    for (start, root, nm) in starts:
        delim = PROBE_DELIM.get(root)
        if delim is None:
            continue
        _REC.clear(); _STRREC.clear(); _RECORDING = True
        try:
            end = delim(zone, start)
        except Exception:
            _RECORDING = False
            continue
        _RECORDING = False
        harvest.append((start, root, nm, end, sorted(set(_REC))))
        for so in _STRREC:
            interior_str.add(so - B5_BASE)
    print('   interior inline-strings harvested from verbatim bodies: %d' % len(interior_str))

    # PASS 2: classify
    per_type_missed = Counter()
    per_type_seen = Counter()
    missed_records = []       # (nm, asset_start, ptr_off, target_off, >=shift_from?, hits_interior_str)
    tgt_interior = 0
    for (start, root, nm, end, pos) in harvest:
        for po in pos:
            if not (start <= po < end):
                continue                      # only pointers inside THIS asset body
            v = struct.unpack_from('>I', zone, po)[0]
            blk, toff = zs.decode_ptr(v)
            if blk != zs.BLOCK_VIRTUAL:
                continue
            if not (0 <= toff < len(zone) - B5_BASE):
                continue                      # out-of-zone => shader/data coincidence, not a ptr
            per_type_seen[root] += 1
            if toff not in registered:
                per_type_missed[root] += 1
                hits = toff in interior_str
                if hits and toff >= shift_from:
                    tgt_interior += 1
                missed_records.append((nm, start, po, toff, toff >= shift_from, hits))

    print('\n== alias pointers harvested per verbatim type (probe-confirmed) ==')
    for t in sorted(per_type_seen):
        print('   %-22s seen=%-6d omap-MISSED=%d' % (t, per_type_seen[t], per_type_missed[t]))

    print('\n== PROVABLE genuine interior pointers ==')
    print('   omap-missed aliases whose target is a harvested interior inline-string: %d'
          % sum(1 for m in missed_records if m[5]))
    print('   of those with target >= shift_from (STALE & provably genuine & safe-to-relink): %d'
          % tgt_interior)

    stale = [m for m in missed_records if m[4]]
    print('\n== omap-MISSED pointers whose target >= shift_from (== STALE after +delta) ==')
    print('   total missed=%d ; of those >= shift_from (would go STALE)=%d'
          % (len(missed_records), len(stale)))
    by_asset = defaultdict(list)
    for nm, start, po, toff, _s, _h in stale:
        by_asset[(nm, start)].append((po, toff))
    for (nm, start), lst in sorted(by_asset.items(), key=lambda kv: kv[0][1])[:40]:
        print('   %-14s @%-9d : %d stale ptr(s) e.g. off@%d -> target@%d'
              % (nm, start, len(lst), lst[0][0], lst[0][1]))
    if not stale:
        print('   (none) -- hypothesis NOT supported for the instrumentable types.')


if __name__ == '__main__':
    main()
