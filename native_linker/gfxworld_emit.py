#!/usr/bin/env python3
"""
emit_gfxworld — Track F's deliverable to the Track G assemble session.

    emit_gfxworld(pc_zone_bytes, pc_gfxworld_off, ctx) -> (bytes, fixups, log)

  bytes  : the complete console GfxWorld (1076B body + all regions) in console
           serialization order, BE, with PC alias values left in pointer words.
  fixups : sorted list of byte offsets (relative to the returned bytes) of
           pointer words holding PC block-5 alias values that the assemble's
           loader-sim omap must rewrite. FOLLOW/INSERT/null pass through as-is.
  log    : list of (region_key, method, size, note) — method tags:
           conv / swap4 / swap2 / verbatim / synth / reencode / template.
           Registered SYNTH/REENCODE rows are the only non-byte-exact classes
           (see CAVEATS_gfxworld_trackF.md).

  ctx (all optional):
    image_source     : callable(name_hash)->iwi dict (PC ipak resolver) — needed
                       for the tail lut material's resident image.
    sampler_lookup   : callable(image_alias, pc_sampler)->console sampler or None.
    validate_against : (console_zone_bytes, console_gfxworld_off) — raid-style
                       oracle diff per region, printed.

Console serialization order (pinned on mp_raid, structure-identical on
mp_dockside): body, streamInfo(trees+leafRefs), skyBoxModel string, sunLight,
volumes, dpvsPlanes, cells, draw.(reflectionProbes, lightmaps, vd0, vd1,
indices), lightGrid, models, materialMemory, sunflare materials, outdoorImage,
shadowGeom, lightRegion, dpvs.(smodelCastsShadow, sortedSurfIndex, smodelInsts,
surfaces, smodelDrawInsts), waterBuffers, tail materials, occluders,
outdoorBounds, heroLights, heroLightTree.
"""
import struct
import sys
import os
import io
import contextlib
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, '..', 'wiiu_ref'))

import gfxworld_probe2 as G2
import gfxworld_dynamics as GD
import gfxworld_regions as GR
import gfxworld_gx2 as GG
import gfxworld_smodel as GM
import gfxworld_streaminfo as GS
import gfxworld_body as GB

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)


def _is_alias(v):
    return 0xA0000000 <= v < 0xC0000000


def _pc_marks(pc, off):
    cfg = dict(G2.CFG['pc'])
    cfg['body'] = off
    p = G2.W.__new__(G2.W)
    p.d = pc; p.c = cfg; p.e = '<'; p.b = off; p.o = off + cfg['bodysize']
    marks = []
    p.mark = lambda l, *a: marks.append((l, p.o))
    with contextlib.redirect_stdout(io.StringIO()):
        G2.walk(p)
    key = lambda l: re.sub(r' x\d+| \d+ bytes|\(\d+\)| @\d+|\[.*\]|\d+', '', l).strip()
    spans = []
    prev = off + cfg['bodysize']
    for l, e in marks:
        spans.append((key(l), prev, e))
        prev = e
    return spans


def _swap4(pc, a, b):
    return GD.swap_n(pc[a:b], 4)


def _ptr_words_fixups(pc, a, b, base, fixups, stride=4, offs=None):
    """Record alias fixups for 4B words at offs (or all) within [a,b)."""
    rng = range(0, b - a, stride) if offs is None else offs
    for o in rng:
        if _is_alias(struct.unpack_from('<I', pc, a + o)[0]):
            fixups.append(base + o)


# console draw section template offsets (console_off_rel396, pc_off_rel396)
_DRAW_COUNTS = [(4, 0), (16, 12), (32, 28), (36, 32), (68, 44), (100, 56)]
_DRAW_FOLLOWS = [8, 12, 20, 24, 28, 44, 76, 104]


def _emit_body(pc, off, tree_count, leafref_count, fixups):
    buf = bytearray(1076)
    # mapped sub-structs + loose runs (alias words: PC value + fixup)
    for nm, coff, poff in GB._SUBSTRUCTS:
        s = GB.Lc.get(nm)['size']
        sub = bytearray(s)
        fx = []
        GB._swap_mapped(pc, nm, nm, off + poff, sub, 0, fx)
        buf[coff:coff + s] = sub
        for c, _tgt in fx:
            fixups.append(coff + c)
    # GB._LOOSE stops at the dpvs structs; the console tail (waterBuffers[2],
    # water/corona/rope/lut material ptrs, occluder/outdoorBounds/heroLight
    # counts+ptrs) maps 1:1 from PC 956..1028 -> console 1004..1076.
    for coff, poff, size in list(GB._LOOSE) + [(1004, 956, 72)]:
        for j in range(0, size, 4):
            v = struct.unpack_from('<I', pc, off + poff + j)[0]
            struct.pack_into('>I', buf, coff + j, v)
            if _is_alias(v):
                fixups.append(coff + j)
    # streamInfo counts/ptrs @20..36
    struct.pack_into('>I', buf, 20, tree_count)
    struct.pack_into('>I', buf, 24, FOLLOW)
    struct.pack_into('>I', buf, 28, leafref_count)
    struct.pack_into('>I', buf, 32, FOLLOW)
    # skyBoxModel @36 (same on PC @36; _LOOSE covers 36 already — keep)
    # draw section @396
    D = 396
    for j in range(D, D + 116, 4):
        struct.pack_into('>I', buf, j, 0)
    for co_, po_ in _DRAW_COUNTS:
        struct.pack_into('>I', buf, D + co_,
                         struct.unpack_from('<I', pc, off + 396 + po_)[0])
    for co_ in _DRAW_FOLLOWS:
        struct.pack_into('>I', buf, D + co_, FOLLOW)
    return bytes(buf)


def emit_gfxworld(pc, off, ctx=None):
    ctx = ctx or {}
    fixups = []
    log = []
    spans = _pc_marks(pc, off)
    S = {}
    for k, a, b in spans:
        S.setdefault(k, []).append((a, b))
    g = lambda o: struct.unpack_from('<I', pc, off + o)[0]

    # --- streamInfo synthesis (needs smodelInsts span) ---
    smc = g(784)
    sminst = S['dpvs.smodelInsts'][0][0]
    streaminfo, tree_count, leafref_count = GS.synth_streaminfo(pc, sminst, smc)

    out = bytearray()

    def emit(key, data, method, note='', fx=None):
        base = len(out)
        if fx:
            fixups.extend(base + x for x in fx)
        out.extend(data)
        log.append((key, method, len(data), note))
        return base

    # --- body ---
    bodyfx = []
    body = _emit_body(pc, off, tree_count, leafref_count, bodyfx)
    emit('body', body, 'template', '1076B synth draw/streamInfo', bodyfx)

    # --- streamInfo (console-only) ---
    emit('streamInfo', streaminfo, 'synth',
         'REGISTERED SYNTH: KD median-split, %d nodes %d refs' % (tree_count, leafref_count))

    # --- skyBoxModel inline string ---
    if g(36) == FOLLOW:
        a, b = S['skyBoxModel'][0]
        emit('skyBoxModel', pc[a:b], 'verbatim')

    # --- sunLight: verbatim word0 + swap4 rest ---
    if 'sunLight' in S:
        a, b = S['sunLight'][0]
        data = pc[a:a + 4] + GD.swap_n(pc[a + 4:b], 4)
        emit('sunLight', data, 'conv')

    # --- volumes (all swap4; fogModVol differs in stride -> hard error) ---
    for key in ('coronas', 'shadowMapVol', 'smVolPlanes', 'exposureVol',
                'expVolPlanes', 'fogVol', 'fogVolPlanes', 'fogModVol',
                'fogModPlanes', 'lutVol', 'lutVolPlanes'):
        if key in S:
            if key == 'fogModVol':
                raise NotImplementedError('fogModVol present: console stride 66 != PC 48')
            a, b = S[key][0]
            emit(key, _swap4(pc, a, b), 'swap4')

    # --- dpvsPlanes ---
    a, b = S['dpvsPlanes.planes'][0]
    emit('dpvsPlanes.planes', GD.swap_fields(pc[a:b], 20, 4), 'conv')
    a, b = S['dpvsPlanes.nodes'][0]
    emit('dpvsPlanes.nodes', GD.swap_n(pc[a:b], 2), 'swap2')

    # --- cells ---
    a, b = S['cells'][0]
    fx = []
    data = GR.conv_cells(pc, a, g(372), fixups=fx, out_base=0)
    emit('cells', data, 'conv', 'PC-built aabb trees kept', fx)

    # --- draw ---
    a, b = S['draw.reflectionProbes'][0]
    fx = []
    data, _ = GG.conv_reflection_probes(pc, a, g(396 + 0), fixups=fx, out_base=0)
    emit('draw.reflectionProbes', data, 'conv', 'inline cube images', fx)
    a, b = S['draw.lightmaps'][0]
    fx = []
    data, _ = GG.conv_lightmaps(pc, a, g(396 + 12), fixups=fx, out_base=0)
    emit('draw.lightmaps', data, 'reencode',
         'REGISTERED REENCODE: RGBA8->BC3 range-fit + 512-block restack', fx)

    # vd0 (grouped) needs the surface/index tables for group bounds
    def _vd0_groups():
        sa, sb = S['dpvs.surfaces'][0]
        ia, ib = S['draw.indices'][0]
        nsurf = (sb - sa) // 80
        nidx = (ib - ia) // 2
        idxarr = struct.unpack('<%dH' % nidx, pc[ia:ia + nidx * 2])
        gmax = {}
        for si in range(nsurf):
            o = sa + si * 80
            o0 = struct.unpack_from('<I', pc, o + 12)[0]
            tc = struct.unpack_from('<H', pc, o + 42)[0]
            bi = struct.unpack_from('<I', pc, o + 44)[0]
            if tc and bi + tc * 3 <= nidx:
                m = max(idxarr[bi:bi + tc * 3])
                if o0 not in gmax or m > gmax[o0]:
                    gmax[o0] = m
        return sorted((o0, m + 1) for o0, m in gmax.items())
    a, b = S['draw.vd.data'][0]
    emit('draw.vd0', GD.conv_world_vertex_grouped(pc[a:b], _vd0_groups()), 'conv',
         'group-aware 36B world verts + cross-lane tangent (lighting_repack)')
    # vd1 is NOT a flat swap2 stream: per-surface-group elements (stride
    # 4/8/12/16) of f16 lightmap-UV words (swap2) + trailing RGBA8 color
    # words (VERBATIM). The old flat swap2 byte-reversed every vertex color
    # (POLISH lighting session; 100% byte-exact raid+dockside).
    import lighting_repack as LR
    a, b = S['draw.vd.data'][1]
    sa, sb = S['dpvs.surfaces'][0]
    ia, ib = S['draw.indices'][0]
    nidx = (ib - ia) // 2
    idxarr = struct.unpack('<%dH' % nidx, pc[ia:ia + nidx * 2])
    vgroups = LR.vd1_groups(pc, sa, (sb - sa) // 80, idxarr, nidx, b - a)
    emit('draw.vd1', LR.conv_vd1(pc[a:b], vgroups), 'conv',
         'per-group f16 UV swap2 + RGBA8 color verbatim')
    a, b = S['draw.indices'][0]
    emit('draw.indices', GD.swap_n(pc[a:b], 2), 'swap2')

    # --- lightGrid ---
    for key, method in (('lightGrid.rowDataStart', 'swap2'),
                        ('lightGrid.rawRowData', 'verbatim'),
                        ('lightGrid.entries', 'entry4'),
                        ('lightGrid.colors', 'verbatim168'),
                        ('lightGrid.coeffs', 'swap2'),
                        ('lightGrid.skyGridVolumes', 'swap4')):
        if key not in S:
            continue
        a, b = S[key][0]
        if method == 'swap2':
            emit(key, GD.swap_n(pc[a:b], 2), 'swap2')
        elif method == 'entry4':
            emit(key, GD.conv_entries(pc[a:b]), 'conv')
        elif method == 'swap4':
            emit(key, _swap4(pc, a, b), 'swap4')
        else:
            emit(key, pc[a:b], 'verbatim')

    # --- models ---
    a, b = S['models'][0]
    fx = []
    _ptr_words_fixups(pc, a, b, len(out), fx)   # XModel aliases inside 64B entries
    emit('models', _swap4(pc, a, b), 'swap4', '', [])
    fixups.extend(fx)

    # --- materialMemory ---
    a, b = S['materialMemory'][0]
    fx = []
    data, _ = GR.conv_material_memory(pc, a, g(572), fixups=fx, out_base=0,
                                      sampler_lookup=ctx.get('sampler_lookup'))
    emit('materialMemory', data, 'conv', 'inline materials (techsets excluded)', fx)

    # --- sunflare materials (inline material assets) ---
    for a, b in S.get('sunflare material inline', []):
        data, _ = GG.conv_tail_material(pc, a, ctx.get('image_source'))
        emit('sunflare material', data, 'conv')

    # --- outdoorImage ---
    if 'outdoorImage inline' in S:
        a, b = S['outdoorImage inline'][0]
        data, _ = GG.conv_outdoor_image(pc, a)
        emit('outdoorImage', data, 'conv')

    # --- shadowGeom / lightRegion ---
    if 'shadowGeom' in S:
        a, b = S['shadowGeom'][0]
        emit('shadowGeom', GD.swap_n(pc[a:b], 2), 'swap2')
    if 'lightRegion' in S:
        a, b = S['lightRegion'][0]
        emit('lightRegion', _swap4(pc, a, b), 'swap4')

    # --- dpvs ---
    a, b = S['dpvs.smodelCastsShadow'][0]
    emit('dpvs.smodelCastsShadow', pc[a:b], 'verbatim')
    a, b = S['dpvs.sortedSurfIndex'][0]
    emit('dpvs.sortedSurfIndex', GD.swap_n(pc[a:b], 2), 'swap2',
         'CAVEAT: PC sort order kept (console re-sorts; draw-order only)')
    a, b = S['dpvs.smodelInsts'][0]
    emit('dpvs.smodelInsts', _swap4(pc, a, b), 'swap4')
    a, b = S['dpvs.surfaces'][0]
    base = len(out)
    fx = [i * 80 + 48 for i in range((b - a) // 80)
          if _is_alias(struct.unpack_from('<I', pc, a + i * 80 + 48)[0])]
    emit('dpvs.surfaces', GD.conv_surface(pc[a:b], 80), 'conv', 'material ptr @48', fx)
    a, b = S['dpvs.smodelDrawInsts'][0]
    fx = []
    data, _ = GM.conv_smodel_draw_insts(pc, a, smc, fixups=fx, out_base=0)
    emit('dpvs.smodelDrawInsts', data, 'conv', 'packed placement 52->28', fx)

    # --- tail ---
    for a, b in S.get('waterBuffer', []):
        emit('waterBuffer', _swap4(pc, a, b), 'swap4')
    for a, b in S.get('tail material inline (body+)', []):
        data, _ = GG.conv_tail_material(pc, a, ctx.get('image_source'))
        emit('tail material', data, 'conv', 'resident lut image')
    for key in ('occluders', 'outdoorBounds', 'heroLights', 'heroLightTree'):
        if key in S:
            a, b = S[key][0]
            emit(key, _swap4(pc, a, b), 'swap4')

    return bytes(out), sorted(fixups), log


# emit-log key -> PC marked-region key, where they differ
_PAIR_KEYMAP = {
    'draw.vd0': 'draw.vd.data',
    'draw.vd1': 'draw.vd.data',
    'outdoorImage': 'outdoorImage inline',
    'tail material': 'tail material inline (body+)',
    'sunflare material': 'sunflare material inline',
}
# console-only regions with no PC span
_PAIR_SKIP = ('streamInfo',)


def region_pairs(pc, off, log):
    """Pair the Track F emit's console regions with their PC source spans
    (part B session 2, HANDOFF item 3: 'region-pair the fine map').

    Returns [(pc_a_abs, pc_b_abs, co_base, co_len, method, key)] in emit
    order — co_base relative to the emitted bytes. Keys resolve through the
    same _pc_marks walk emit_gfxworld used; multi-span keys (vd, waterBuffer,
    sunflare/tail materials) consume their PC spans in order, which matches
    the emit order by construction. The CONSUMER decides interior mapping:
    co_len == pc_len -> linear/exact; size-changing regions map start-only
    (except smodelDrawInsts: fixed 52->28 element scale)."""
    spans = _pc_marks(pc, off)
    S = {}
    for k, a, b in spans:
        S.setdefault(k, []).append((a, b))
    S['body'] = [(off, off + G2.CFG['pc']['bodysize'])]
    used = {}
    pairs = []
    co = 0
    for (key, method, size, note) in log:
        if key in _PAIR_SKIP:
            co += size
            continue
        pk = _PAIR_KEYMAP.get(key, key)
        lst = S.get(pk)
        i = used.get(pk, 0)
        if lst is None or i >= len(lst):
            raise RuntimeError('region_pairs: no PC span for emit key %r' % key)
        used[pk] = i + 1
        a, b = lst[i]
        pairs.append((a, b, co, size, method, key))
        co += size
    return pairs


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '../mp_skate_pc.zone'
    off = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    pc = open(os.path.join(_HERE, path) if not os.path.isabs(path) else path, 'rb').read()
    if off is None:
        import pc_walk
        spans = []
        pc_walk.walk_pc_zone(os.path.join(_HERE, path), spans=spans)
        off = next(s[2] for s in spans if s[1] == 'GFXWORLD')
    out, fixups, log = emit_gfxworld(pc, off)
    print('emitted %d bytes (%.1f MB), %d alias fixups' % (len(out), len(out) / 1e6, len(fixups)))
    for k, m, sz, note in log:
        print('  %-26s %-10s %9d  %s' % (k, m, sz, note))
