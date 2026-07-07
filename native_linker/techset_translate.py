#!/usr/bin/env python3
"""
Track B: Techset PC->Wii U genuine-substitution layer.

Strategy (HANDOFF Track B): do NOT recompile shaders. For every techset a PC map
needs, substitute the genuine console techset blob of the same name, extracted
self-contained (alias-free) by wiiu_ref/techset_extract.py. Names are the
platform-independent join key. Most techsets are shared engine shaders living in
common_mp (which ships on Wii U), so exact-name match covers most of any map.

This module:
  1. build_corpus()  -> name -> genuine self-contained blob, from all console
     zones, selfchecked (zero alias pointers, re-parse == len). Cached to disk.
  2. pc_techset_names(pc_zone) -> ordered set of techset names the PC map declares.
  3. translate(pc_zone) -> per-map coverage: matched-by-name / signature / unmatched.

Signature fallback (step 3 of the handoff) is stubbed behind sig_match(): grouped
by structural signature so map-unique techsets still resolve to a compatible real
blob. Every fallback is recorded so coverage stays honest.
"""
import os
import sys
import glob
import json
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'wiiu_ref'))
sys.path.insert(0, HERE)

import techset_extract as TE          # noqa: E402
import shader_probe as SP             # noqa: E402
import techset_pc as PC               # noqa: E402

# Genuine console corpus sources, most-shared/most-authoritative first so dedup
# keeps the common_mp (engine-shared) copy over per-map duplicates. lit_sm terrain
# blends live in per-MAP zones (not common_mp), so we pull EVERY console zone we can
# decrypt — every outdoor map carries 100+ unique lit_sm techsets.
_OFF = 'wiiu_ref/Original FF'
CONSOLE_ZONES = [
    # shared engine first
    'common_mp.zone',
    # already-staged console map zones
    'wiiu_ref/mp_raid_genuine.zone',
    'wiiu_ref/zm_transit_original.zone',
    'wiiu_ref/mp_dockside_wiiu.zone',
    _OFF + '/mp_la.zone',
    _OFF + '/mp_carrier.zone',
    _OFF + '/faction_cd_mp.zone',
    _OFF + '/faction_fbi_mp.zone',
    _OFF + '/faction_isa_mp.zone',
    _OFF + '/faction_multiteam_mp.zone',
    # stock maps decrypted for corpus expansion (terrain-shader rich)
    _OFF + '/mp_drone.zone',
    _OFF + '/mp_express.zone',
    _OFF + '/mp_hijacked.zone',
    _OFF + '/mp_meltdown.zone',
    _OFF + '/mp_nightclub.zone',
    _OFF + '/mp_overflow.zone',
    _OFF + '/mp_slums.zone',
    _OFF + '/mp_socotra.zone',
    _OFF + '/mp_turbine.zone',
    _OFF + '/mp_village.zone',
]

CORPUS_DIR = os.path.join(ROOT, 'wiiu_ref', 'techset_corpus')
CORPUS_INDEX = os.path.join(CORPUS_DIR, 'index.json')


# --------------------------------------------------------------------------- #
#  Step 1: build the genuine-blob corpus
# --------------------------------------------------------------------------- #
def build_corpus(zones=None, out_dir=CORPUS_DIR, verbose=True):
    """Extract every genuine console techset as a self-contained blob and store
    name -> blob. Dedup by name (first zone wins). Selfcheck each emitted blob;
    reject any that fail (no silent alias leakage). Returns dict name->path."""
    zones = zones or CONSOLE_ZONES
    os.makedirs(out_dir, exist_ok=True)
    index = {}          # name -> {zone, path, size, kind}
    totals = {'name_new': 0, 'dup': 0, 'fail': 0, 'ref': 0}
    for z in zones:
        zp = z if os.path.isabs(z) else os.path.join(ROOT, z)
        if not os.path.exists(zp):
            if verbose:
                print('  skip (missing):', z)
            continue
        d = open(zp, 'rb').read()
        ex = TE.Extractor(d)
        zid = os.path.basename(zp)
        names = sorted(set(ex.techsets) | set(ex.refsets))
        for nm in names:
            if nm in index:
                totals['dup'] += 1
                continue
            try:
                blob = ex.emit_techset(nm)
            except Exception as e:                      # noqa: BLE001
                totals['fail'] += 1
                continue
            if blob is None:
                totals['fail'] += 1
                continue
            kind = 'inline'
            if nm in ex.techsets:
                try:
                    TE.selfcheck(blob)                  # zero-alias invariant
                except Exception:                       # noqa: BLE001
                    totals['fail'] += 1
                    continue
            else:
                kind = 'ref'
                totals['ref'] += 1
            safe = nm.replace('/', '__').replace('\\', '__')
            path = os.path.join(out_dir, safe + '.techset')
            with open(path, 'wb') as f:
                f.write(blob)
            index[nm] = {'zone': zid, 'path': os.path.relpath(path, ROOT),
                         'size': len(blob), 'kind': kind,
                         'sig': _signature(blob) if kind == 'inline' else None}
            totals['name_new'] += 1
        if verbose:
            print('  %-32s -> corpus now %d names (%s)'
                  % (zid, len(index), dict(totals)))
    with open(CORPUS_INDEX, 'w') as f:
        json.dump(index, f, indent=0)
    if verbose:
        print('corpus: %d unique techset names  (%s)' % (len(index), dict(totals)))
    return index


def load_corpus():
    if not os.path.exists(CORPUS_INDEX):
        raise RuntimeError('no corpus; run build_corpus() first')
    with open(CORPUS_INDEX) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
#  Structural signature (for step-3 signature fallback)
# --------------------------------------------------------------------------- #
def _signature(blob):
    """Structural fingerprint of a console techset: (technique slot mask,
    per-technique passCount tuple). Two techsets with the same signature are
    layout-compatible substitutes."""
    try:
        mask = 0
        passes = []
        c = SP.Cur(blob, 136)
        c.cstr(160)
        slots = [struct.unpack('>I', blob[8 + i * 4:12 + i * 4])[0]
                 for i in range(32)]
        for i, v in enumerate(slots):
            if v != SP.FOLLOW if hasattr(SP, 'FOLLOW') else v != 0xFFFFFFFF:
                continue
            mask |= (1 << i)
            pc = struct.unpack('>H', blob[c.o + 6:c.o + 8])[0]
            passes.append(pc)
            c.o = _tech_end(blob, c.o)
        return '%08x:%s' % (mask, ','.join(map(str, passes)))
    except Exception:                                   # noqa: BLE001
        return None


def _tech_end(blob, t):
    """Best-effort MaterialTechnique span in an emitted blob for signature use."""
    pc = struct.unpack('>H', blob[t + 6:t + 8])[0]
    return t + 8 + pc * 24        # header + passes only (enough for signature)


# Platform-independent structural signature. PC has 36 technique slots, console
# 32 (the stateBitsEntry 36->32 mirror), and the slot-remap table is not fully
# known, so a slot-index-based mask is NOT comparable across platforms. Instead we
# use (#present techniques, sorted passCounts) which is identical on both sides —
# it captures blend structure (layer count => passCount profile) without slot ids.
def pi_sig_console(blob):
    """(#present, sorted passcounts) for a genuine console techset blob."""
    try:
        c = SP.Cur(blob, 136)
        c.cstr(160)
        slots = [struct.unpack('>I', blob[8 + i * 4:12 + i * 4])[0] for i in range(32)]
        passes = []
        for v in slots:
            if v != SP.FOLLOW:
                continue
            passes.append(SP.u16(blob, c.o + 6))
            c.o = SP.parse_technique(blob, c.o)         # advance to next technique
        return (len(passes), tuple(sorted(passes)))
    except Exception:                                   # noqa: BLE001
        return None


def pi_sig_pc(d, off):
    """(#present, sorted passcounts) for a PC MaterialTechniqueSet at off."""
    try:
        passes = []
        o = off + PC.TS_BODY
        if PC._u32(d, off) in PC.PTRS:
            o = d.index(b'\x00', o) + 1
        for i in range(36):
            if PC._u32(d, off + 8 + i * 4) not in PC.PTRS:
                continue
            tb = o
            pc = PC._u16(d, tb + 6)
            passes.append(pc)
            o = PC._technique_span(d, tb)
        return (len(passes), tuple(sorted(passes)))
    except Exception:                                   # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
#  Step 2: enumerate PC techset names the target map declares
# --------------------------------------------------------------------------- #
def pc_techset_names_walk(path):
    """Authoritative: drive the PC asset-list sequential walk (same machinery as
    pc_walk.walk_pc_zone) and record every inline-bodied MaterialTechniqueSet's
    real body offset + name@0. Returns (names, drift). Aliased techset assets
    (hp != FOLLOW) carry no inline body/name here; they resolve against already-
    loaded zones (common_mp) at load and never dangle."""
    import pc_walk  # noqa: E402  (heavy deps; import on demand)
    import struct_layout, walker as W, pc_zone as PZ
    import fx_pc, xmodel_pc, lightdef_pc, gfxworld_pc, glasses_pc, clipmap_pc, material_convert
    import destructibledef_probe as _DP, gameworldmp_probe as _GW

    PCb = open(path, 'rb').read()
    r = PZ.PCZoneReader(PCb); r.read_string_table(); r.read_asset_list()
    L = struct_layout.Layout(W.HDR, console=False)
    zc = W.ZoneCode(W.ZC_DIR)
    wk = W.Walker(PCb, L, zc, r.block_sizes)
    wk.u16 = lambda o: struct.unpack_from('<H', PCb, o)[0]
    wk.u32 = lambda o: struct.unpack_from('<I', PCb, o)[0]
    wk._scalar = lambda base, o: (lambda s: PCb[o] if s == 1 else
                                  struct.unpack_from('<H' if s == 2 else '<I', PCb, o)[0])(L._resolve(base)[0])
    cur = r.assets_end
    names, drift = [], None
    for i, (t, nm, hp) in enumerate(r.assets):
        root = W.ASSET_ROOT.get(nm)
        if root is None or root not in L.structs or hp != PC.FOLLOW:
            continue
        start = cur
        try:
            if root == 'MaterialTechniqueSet':
                names.append((_pc_name(PCb, start) or '<noname@0x%x>' % start, start))
                cur = PC.parse_techset_pc(PCb, start)
            elif root == 'FxEffectDef':
                cur, _ = fx_pc.parse_fx_pc(PCb, start)
            elif root == 'XModel':
                cur = xmodel_pc.parse_xmodel_pc(PCb, start)
            elif root == 'DestructibleDef':
                cur = _DP.parse_destructible(PCb, start, '<')[0]
            elif root == 'GfxLightDef':
                cur = lightdef_pc.parse_lightdef_pc(PCb, start)
            elif root == 'GfxWorld':
                cur = gfxworld_pc.parse_gfxworld_pc(PCb, start)
            elif root == 'GameWorldMp':
                cur = _GW.Walker(PCb, '<', 144).walk(start)[0]
            elif root == 'Glasses':
                cur = glasses_pc.parse_glasses_pc(PCb, start)
            elif root == 'clipMap_t':
                cur = clipmap_pc.parse_clipmap_pc(PCb, start)
            elif root == 'Material':
                _, cur = material_convert.convert_material(PCb, start)
            else:
                cur = wk.walk(root, cur)
        except Exception as e:                          # noqa: BLE001
            drift = (i, nm, start, 'EXC: %s' % e)
            break
    return names, drift


def pc_techset_names(pc_zone):
    """Heuristic byte-scan fallback (no walk). Under-counts vs the asset-list
    walk; use pc_techset_names_walk for authoritative enumeration."""
    d = open(pc_zone, 'rb').read() if isinstance(pc_zone, str) else pc_zone
    names = []
    seen = []
    i = -1
    # PC techset bodies start with a FOLLOW/INSERT name pointer.
    needle = struct.pack('<I', PC.FOLLOW)
    while True:
        i = d.find(needle, i + 1)
        if i < 0:
            break
        if any(a <= i < b for a, b in seen):
            continue
        if not _looks_like_pc_techset(d, i):
            continue
        try:
            end = PC.parse_techset_pc(d, i)
        except Exception:                               # noqa: BLE001
            continue
        nm = _pc_name(d, i)
        if nm is None:
            continue
        seen.append((i, end))
        names.append(nm)
    return names


NAME_CHARS = set(range(0x20, 0x7f))


# In an unlinked zone stream every pointer field is one of these sentinels:
# streamed-inline (FOLLOW), reuse-previous (INSERT), or null. Never an address.
SLOT_OK = (0, PC.FOLLOW, PC.INSERT)


def _looks_like_pc_techset(d, o):
    if o + PC.TS_BODY > len(d):
        return False
    if PC._u32(d, o) != PC.FOLLOW:          # name ptr always streams inline
        return False
    if PC._u32(d, o + 4) > 0x40:            # worldVertFormat: small enum
        return False
    follow = 0
    for k in range(36):                     # 36 technique slots
        v = PC._u32(d, o + 8 + k * 4)
        if v not in SLOT_OK:
            return False                    # a real address here => not a techset
        if v == PC.FOLLOW:
            follow += 1
    return follow >= 1


def _pc_name(d, o):
    """Techset name string follows the 152-byte body (name ptr FOLLOW)."""
    if PC._u32(d, o) not in PC.PTRS:
        return None
    e = d.index(b'\x00', o + PC.TS_BODY)
    raw = d[o + PC.TS_BODY:e]
    if not raw or any(b not in NAME_CHARS for b in raw):
        return None
    return raw.decode('latin-1')


# --------------------------------------------------------------------------- #
#  Step 3/D: name-grammar structural fallback
# --------------------------------------------------------------------------- #
# The blob passcount signature is NOT platform-portable: PC has 36 technique
# slots, console 32 (the stateBitsEntry 36->32 mirror), so the same shader has a
# different #present on each side (verified: mc_lit_sm_t0c0 = 28 PC / 25 console).
# The platform-INDEPENDENT structural key is the techset NAME grammar itself:
# a lit_sm-family name encodes base + layer count + per-layer map set, and the
# same string is used on PC and console. Substituting a same-structure console
# techset is CORRECT (not lossy) for these blends: the techset is the shader; the
# textures are bound separately by the material, so a same-layer-count console
# blend renders with the map's own textures still bound.
import re as _re

_MAPGROUP = _re.compile(r'^([a-z]\d)+$')      # e.g. r0c0n0x0, b1c1, b2c2v2


def name_struct(nm):
    """Parse a techset name into (family_prefix, [layer map-sets]). Returns None
    if it isn't a layered map-grammar name. Trailing _<hash> is stripped."""
    parts = nm.split('_')
    if len(parts) < 2:
        return None
    # drop trailing hash segment (alnum, not a clean map-group)
    if not _MAPGROUP.match(parts[-1]):
        parts = parts[:-1]
    # the trailing contiguous run of map-group segments = the layers
    layers = []
    while parts and _MAPGROUP.match(parts[-1]):
        grp = parts.pop()
        # map-set = the set of letters (ignoring the per-layer index digit)
        letters = frozenset(_re.findall(r'([a-z])\d', grp))
        layers.insert(0, letters)
    if not layers:
        return None
    family = '_'.join(parts)
    return (family, layers)


def _struct_score(a, b):
    """Similarity of two name_struct results. Same layer count required for a
    non-negative score; adds per-layer map-set Jaccard + family-match bonus."""
    fa, la = a
    fb, lb = b
    if len(la) != len(lb):
        return -1.0
    s = 2.0 if fa == fb else 0.0
    for xa, xb in zip(la, lb):
        u = len(xa | xb)
        s += (len(xa & xb) / u) if u else 1.0
    return s


def build_struct_index(corpus):
    """corpus name -> name_struct, only for parseable layered names."""
    out = {}
    for nm in corpus:
        st = name_struct(nm)
        if st:
            out[nm] = st
    return out


def _strip_hash(nm):
    parts = nm.split('_')
    if parts and _re.fullmatch(r'[a-z0-9]{6,10}', parts[-1]) and _re.search(r'\d', parts[-1]) \
            and not _MAPGROUP.match(parts[-1]):
        parts = parts[:-1]
    return parts


def prefix_fallback(pc_name, corp_names):
    """For non-layered special shaders (treecanopy, sw4_3d_*, superflare...),
    substitute the console techset sharing the longest leading-token prefix
    (hash-stripped). Visually approximate but structurally a real console blob."""
    want = _strip_hash(pc_name)
    if not want:
        return None
    best, best_n = None, 0
    for cn in corp_names:
        cp = _strip_hash(cn)
        k = 0
        for a, b in zip(want, cp):
            if a != b:
                break
            k += 1
        # require sharing the semantic core (>=2 leading tokens, e.g. 'sw4_3d')
        if k >= 2 and (k > best_n or (k == best_n and best and len(cn) < len(best))):
            best, best_n = cn, k
    return (best, float(best_n), 'prefix') if best else None


def struct_fallback(pc_name, struct_index, corp_names=None):
    """Find the best console substitute for an unmatched PC techset. Returns
    (console_name, score, kind) where kind in {'struct','downmap','prefix'}, or
    None if nothing resolves."""
    want = name_struct(pc_name)
    if want is None:
        return prefix_fallback(pc_name, corp_names) if corp_names else None
    best, best_s = None, -1.0
    for cn, st in struct_index.items():
        sc = _struct_score(want, st)
        if sc > best_s or (sc == best_s and best and len(cn) < len(best)):
            best, best_s = cn, sc
    if best is not None and best_s >= 0.0:
        return (best, best_s, 'struct')
    # no same-layer-count console techset -> structural down-map to nearest
    # lower layer count (the true Wii U layer ceiling).
    wf, wl = want
    cand = None
    for cn, (cf, cl) in struct_index.items():
        if len(cl) < len(wl) and (cand is None or len(cl) > len(cand[1])):
            cand = (cn, cl)
    if cand:
        return (cand[0], 0.0, 'downmap')
    return None


# --------------------------------------------------------------------------- #
#  translate a PC map -> full coverage report (exact / fallback / downmap)
# --------------------------------------------------------------------------- #
def translate(pc_zone, corpus=None, verbose=True, use_walk=True):
    corpus = corpus or load_corpus()
    corp_names = set(corpus)
    struct_index = build_struct_index(corp_names)

    if use_walk:
        pairs, drift = pc_techset_names_walk(pc_zone)
        names = [n.lstrip(',') for (n, _off) in pairs if not n.startswith('<')]
    else:
        names, drift = [n.lstrip(',') for n in pc_techset_names(pc_zone)], None

    uniq = sorted(set(names))
    report = {'zone': os.path.basename(pc_zone) if isinstance(pc_zone, str) else '<bytes>',
              'total': len(uniq), 'by_name': [], 'by_struct': {}, 'downmap': {},
              'prefix': {}, 'unresolved': [], 'drift': drift}
    bucket = {'struct': report['by_struct'], 'downmap': report['downmap'],
              'prefix': report['prefix']}
    for nm in uniq:
        if nm in corp_names:
            report['by_name'].append(nm)
            continue
        fb = struct_fallback(nm, struct_index, corp_names)
        if fb is None:
            report['unresolved'].append(nm)
        else:
            bucket[fb[2]][nm] = (fb[0], round(fb[1], 3))
    if verbose:
        t = report['total']
        bn, bs, dm, pf, un = (len(report['by_name']), len(report['by_struct']),
                              len(report['downmap']), len(report['prefix']),
                              len(report['unresolved']))
        print('%-22s techsets=%d  exact=%d(%.1f%%)  struct-sub=%d  downmap=%d  prefix-sub=%d  UNRESOLVED=%d%s'
              % (report['zone'], t, bn, 100.0 * bn / t if t else 0.0, bs, dm, pf, un,
                 '  [walk drift @asset %d]' % drift[0] if drift else ''))
    return report


def emit_manifest(pc_zone, corpus=None, out_path=None, verbose=True):
    """Produce the full PC->console techset substitution manifest for a map and
    verify every delivered console blob re-parses with ZERO alias pointers
    (Track B invariant). Returns the manifest dict. Each entry: pc_name ->
    {console, method, score}. method in exact/struct/downmap/prefix."""
    corpus = corpus or load_corpus()
    r = translate(pc_zone, corpus=corpus, verbose=False)
    manifest = {}
    for nm in r['by_name']:
        manifest[nm] = {'console': nm, 'method': 'exact', 'score': None}
    for method, key in (('struct', 'by_struct'), ('downmap', 'downmap'), ('prefix', 'prefix')):
        for pc, (cn, sc) in r[key].items():
            manifest[pc] = {'console': cn, 'method': method, 'score': sc}
    # verify every delivered blob selfchecks (zero-alias, re-parse == len)
    bad = []
    checked = 0
    for pc, m in manifest.items():
        meta = corpus.get(m['console'])
        if meta is None:
            bad.append((pc, 'no corpus blob for %s' % m['console']))
            continue
        if meta['kind'] != 'inline':
            continue    # ref-encoded blobs are verbatim 136B bodies, no technique tree
        blob = open(os.path.join(ROOT, meta['path']), 'rb').read()
        try:
            TE.selfcheck(blob)
            checked += 1
        except Exception as e:                          # noqa: BLE001
            bad.append((pc, 'selfcheck %s: %s' % (m['console'], e)))
    result = {'zone': r['zone'], 'total': r['total'],
              'exact': len(r['by_name']), 'struct': len(r['by_struct']),
              'downmap': len(r['downmap']), 'prefix': len(r['prefix']),
              'unresolved': r['unresolved'], 'drift': r['drift'],
              'blobs_selfchecked': checked, 'selfcheck_failures': bad,
              'map': manifest}
    if out_path:
        with open(out_path, 'w') as f:
            json.dump(result, f, indent=1)
    if verbose:
        print('%s: %d techsets -> exact=%d struct=%d downmap=%d prefix=%d unresolved=%d'
              % (r['zone'], r['total'], result['exact'], result['struct'],
                 result['downmap'], result['prefix'], len(r['unresolved'])))
        print('  substitute blobs selfchecked (zero-alias): %d, failures: %d'
              % (checked, len(bad)))
        if bad:
            for pc, why in bad[:10]:
                print('   FAIL %s: %s' % (pc, why))
    return result


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'build'
    if cmd == 'manifest':
        out = sys.argv[3] if len(sys.argv) > 3 else None
        emit_manifest(sys.argv[2], out_path=out)
        raise SystemExit(0)
    if cmd == 'build':
        build_corpus()
    elif cmd == 'translate':
        r = translate(sys.argv[2])
        for k in ('by_struct', 'downmap', 'prefix'):
            if r[k]:
                print('  --- %s ---' % k)
                for pc, cn in r[k].items():
                    print('    %-46s -> %s' % (pc, cn))
        if r['unresolved']:
            print('  UNRESOLVED:', r['unresolved'])
    elif cmd == 'names':
        for n, off in pc_techset_names_walk(sys.argv[2])[0]:
            print(n)
