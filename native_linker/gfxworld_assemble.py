#!/usr/bin/env python3
"""
GfxWorld ASSEMBLER: walk PC GfxWorld region-by-region, convert each region PC->console
per the validated REGION_SPEC, and place it at the console offset. Validates the
walk->convert->reassemble machinery against the genuine mp_raid 22MB oracle.

Strategy for VALIDATION (Raid): start from the genuine console GfxWorld as baseline
(so console-specific/reorder/GX2 regions we haven't wired keep genuine bytes and stay
consistent), then OVERWRITE the byte-convertible regions with output produced from the
PC source. Every byte-convertible region == genuine (proven), so a correct assembler
reproduces the genuine GfxWorld exactly -> a byte-identical result proves the region
walk + dispatch + conversion + placement are all correct. Coverage = how many bytes were
genuinely produced from PC (vs baseline-reused) — that is the real PC->console footprint.

For a DLC map (no genuine baseline) the same walk drives full conversion + the 4 small
generators (smodelDrawInsts lmapVertexInfo, materialMemory, cell portals, streamInfo).
"""
import sys, os, io, contextlib, re, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import gfxworld_probe2 as G2
import gfxworld_dynamics as GD


_WREF = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref')


def walk(cfgname):
    cfg = dict(G2.CFG[cfgname])
    path = cfg['path'] if os.path.isabs(cfg['path']) else os.path.join(_WREF, cfg['path'])
    d = open(path, 'rb').read()
    p = G2.W.__new__(G2.W); p.c = cfg; p.d = d; p.e = cfg['endian']
    p.b = cfg['body']; p.o = cfg['body'] + cfg['bodysize']
    m = []
    p.mark = lambda l, *a: m.append((l, p.o))
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            G2.walk(p)
        except Exception:
            pass
    return m, d, cfg


def _key(l):
    return re.sub(r' x\d+| \d+ bytes|\(\d+\)| @\d+|\[.*\]|\d+', '', l).strip()


def _spans(marks, body_end):
    out = []; prev = body_end
    for l, e in marks:
        out.append((_key(l), prev, e)); prev = e
    return out


def convert_region(method, params, pc_bytes):
    """Return converted console bytes for a region, or None to reuse the baseline."""
    if method == 'swap4':
        return GD.swap_n(pc_bytes, 4)
    if method == 'swap2':
        return GD.swap_n(pc_bytes, 2)
    if method == 'fields':
        st = params.get('stride'); sw = params.get('swap_words')
        if st and sw:
            return GD.swap_fields(pc_bytes, st, sw)
        return None                         # unspecified field struct -> reuse for now
    if method == 'entry4':
        return GD.conv_entries(pc_bytes)
    if method == 'surface':
        return GD.conv_surface(pc_bytes, params.get('stride', 80))
    if method == 'world_vertex':
        # vd0 = 36B world verts (conv_world_vertex handles a non-36-multiple tail gracefully).
        # vd1 (2nd 'draw.vd.data' span) is a DIFFERENT format and is excluded by the caller
        # (occurrence gating) so it stays UNCONVERTED rather than mis-converted as 36B.
        return GD.conv_world_vertex(pc_bytes)
    # reorder_pc / console_gx2 / reuse / gen -> baseline for the Raid validation
    return None


def assemble(validate=True, skip_convert=()):
    # skip_convert: region keys forced to keep the genuine baseline (not PC-converted). Used to
    # isolate variables in a hardware diagnostic build (e.g. skip 'dpvs.surfaces' to test converted
    # vd0/vd1/indices against GENUINE surface bounds/material ptrs, removing the zero-bounds confound).
    cm, CO, ccfg = walk('wiiu')
    pm, PC, pcfg = walk('pc')
    cbody = ccfg['body']; cbody_end = cbody + ccfg['bodysize']
    pbody = pcfg['body']; pbody_end = pbody + pcfg['bodysize']
    cspans = _spans(cm, cbody_end)
    pspans = _spans(pm, pbody_end)
    # Pair PC spans to console spans by KEY, but consume duplicate keys in ORDER (a plain dict
    # collapses duplicates: vd0 and vd1 both key to 'draw.vd.data'). A per-key FIFO handles both
    # duplicate keys (vd0 then vd1) and console-only regions PC lacks (e.g. streamInfo 'gen').
    from collections import defaultdict, deque
    pqueue = defaultdict(deque)
    for k, a, b in pspans:
        pqueue[k].append((a, b))
    CONVERT_METHODS = ('swap4', 'swap2', 'fields', 'entry4', 'surface', 'world_vertex')

    # vd0 group layout (PC): each surface vertex GROUP = vertexCount*36 then pad to 16B; convert
    # per-group, not flat. Groups keyed by PC vertexDataOffset0@12; vertexCount = max(index)+1 over
    # the group's surfaces (0-relative indices). Built from the PC surface + index spans.
    def _find_span(key):
        for kk, a, b in pspans:
            if kk == key:
                return a, b
        return None
    vd0_groups = []
    _surf = _find_span('dpvs.surfaces'); _idxs = _find_span('draw.indices')
    if _surf and _idxs:
        sa, sb = _surf; ia, ib = _idxs
        nsurf = (sb - sa) // 80
        nidx = (ib - ia) // 2
        idxarr = struct.unpack('<%dH' % nidx, PC[ia:ia + nidx * 2])
        gmax = {}
        for si in range(nsurf):
            o = sa + si * 80
            o0 = struct.unpack_from('<I', PC, o + 12)[0]
            tc = struct.unpack_from('<H', PC, o + 42)[0]
            bi = struct.unpack_from('<I', PC, o + 44)[0]
            if tc and bi + tc * 3 <= nidx:
                m = max(idxarr[bi:bi + tc * 3])
                if o0 not in gmax or m > gmax[o0]:
                    gmax[o0] = m
        vd0_groups = sorted((o0, m + 1) for o0, m in gmax.items())

    gw_end = cspans[-1][2]
    out = bytearray(CO[cbody:gw_end])       # baseline = genuine console GfxWorld
    base = cbody
    converted = reused = 0
    log = []
    vd_seen = {}
    for i, (k, ca, cb) in enumerate(cspans):
        csize = cb - ca
        if csize <= 0:
            continue
        method, params = GD.REGION_SPEC.get(k, ('reuse', {}))
        if k in skip_convert:
            method = 'reuse'            # keep genuine baseline for this region (diagnostic isolation)
        # vd0/vd1 share key 'draw.vd.data'; only the FIRST occurrence (vd0) is the 36B world-vertex
        # stream. Force the 2nd (vd1) to a non-convert so it is explicitly UNCONVERTED, not
        # mis-converted as 36B nor silently baseline-reused.
        if method == 'world_vertex':
            vd_seen[k] = vd_seen.get(k, 0) + 1
            if vd_seen[k] > 1:
                method = 'swap2'   # 2nd 'draw.vd.data' span = vd1 (stride 4 = 2x u16 -> swap2)
        pcspan = pqueue[k].popleft() if pqueue[k] else None
        conv = None
        if pcspan and method in CONVERT_METHODS:
            pa, pb = pcspan
            pc_bytes = PC[pa:pa + csize] if (pb - pa) >= csize else PC[pa:pb]
            if len(pc_bytes) == csize:
                if method == 'world_vertex':          # vd0: group-aware (16B group padding)
                    conv = GD.conv_world_vertex_grouped(pc_bytes, vd0_groups)
                else:
                    conv = convert_region(method, params, pc_bytes)
        if conv is not None and len(conv) == csize:
            out[ca - base:cb - base] = conv
            converted += csize
            log.append((k, method, csize, 'CONVERTED'))
        else:
            # distinguish an explicit non-conversion (e.g. vd1 under world_vertex) from a plain
            # baseline-reuse region, so the vd0/vd1 collision cannot mask an unconverted stream.
            tag = 'UNCONVERTED' if method in CONVERT_METHODS or method == 'reuse_vd1' else 'reused'
            reused += csize
            log.append((k, method, csize, tag))

    total = gw_end - cbody
    if validate:
        genuine = CO[cbody:gw_end]
        match = bytes(out) == genuine
        # find first divergence among CONVERTED regions
        firstdiff = next((i for i in range(len(out)) if out[i] != genuine[i]), -1)
        print("GfxWorld assembled: %d bytes (%.1f MB)" % (total, total / 1e6))
        print("  PC-converted: %d bytes (%.1f MB, %.0f%%)  reused-baseline: %d bytes"
              % (converted, converted / 1e6, 100.0 * converted / total, reused))
        print("  byte-identical to genuine oracle: %s%s"
              % (match, "" if match else "  (first diff @0x%x)" % firstdiff))
        print("  --- region dispatch ---")
        # per-region oracle match rate (only meaningful for CONVERTED / UNCONVERTED spans)
        rate = {}
        pos = 0
        for k, method, sz, st in log:
            if st in ('CONVERTED', 'UNCONVERTED'):
                seg_o = out[pos:pos + sz]
                seg_g = genuine[pos:pos + sz]
                dif = sum(1 for j in range(sz) if seg_o[j] != seg_g[j])
                rate[(k, pos)] = (sz - dif, sz)
            pos += sz
        pos = 0
        for k, method, sz, st in log:
            tagmap = {'CONVERTED': 'PC', 'UNCONVERTED': '!!', 'reused': '..'}
            tag = tagmap.get(st, '..')
            extra = ''
            if (k, pos) in rate:
                m, t = rate[(k, pos)]
                extra = '  oracle-match %.2f%% (%d/%d B)' % (100.0 * m / t, m, t)
            print("   [%s] %-22s %-12s %9d%s" % (tag, k, method, sz, extra))
            pos += sz
    return bytes(out)


if __name__ == '__main__':
    assemble()
