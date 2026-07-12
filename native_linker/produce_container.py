#!/usr/bin/env python3
"""
CONTAINER AUTHOR (Track G, final assemble stage). Authors the REAL console
zone around the no-backbone body emit (produce_nobackbone.assemble_zone):
script-string table (PC verbatim — proven byte-equal to genuine), console
XAsset array (type remap + MP inserts), XFile header + block sizes, body
stream in true console order (english bank threaded through the pass-3 sim).

  author_zone(pc_path, map_name) -> (zone_bytes, info)
  raid_dryrun()  : author the raid container and diff every container level
                   (strings, array rows, hp aliases, header words) against
                   mp_raid_genuine + re-walk our own zone. Mandated first gate.

MP insert set (pinned vs mp_raid_genuine, 889 = 887 + 2):
  * GLASSES ALIAS row at console index 1. Its hp is a stale linker-heap
    don't-care (raid 0xe1af0513 "block 7", dockside 0x41b01f13 "block 2" —
    arbitrary values into zero-sized blocks; loader resolves aliases by name).
    We carry raid's genuine word verbatim.
  * PC GLASSES asset relabels to MAP_ENTS (console type 47), body stays inline.
  * localized SndBank row + body (mpl_<map>.english, author_english_bank)
    inserted BEFORE the main SOUND row/body (genuine: .english @871, .all @872).

Header block sizes (measured raid+dockside genuine):
  block0 = 4780, block2 = 12,976,128 : MP CONSTANTS (fixed pools)
  block1 (RT_TEMP) varies/unmodeled  : carry raid's 2,969,732 (>= dockside;
                                       registered approximation, boot sheet)
  block5 = our pass-3 sim total + SAFETY_B5 margin (sim under-reads genuine by
           1,065 raid / 18,934 dock; undersize is fatal, oversize is safe)
"""
import sys, os, struct
sys.path.insert(0, '.'); sys.path.insert(0, os.path.join('..', 'wiiu_ref'))
import pc_zone, wiiu_zone
import produce_nobackbone as PN
import smalls_convert as SC
import _assetlist_author as ALA

FOLLOW = 0xFFFFFFFF
B5_BASE = 64
GLASSES_ALIAS_HP = 0xe1af0513          # genuine raid stale-heap word (don't-care)
BLOCK0_MP = 4780
BLOCK1_MP = 2969732                    # raid genuine (registered approximation)
BLOCK2_MP = 12976128
SAFETY_B5 = 262144                     # block-5 allocation margin


def _pc_string_region(PC, rp):
    """(ptr_words, inline_bytes): the script-string table exactly as PC
    serializes it — reused verbatim on console (proven byte-equal)."""
    sc = rp.string_count
    o = 64
    ptrs = list(struct.unpack_from('<%dI' % sc, PC, o))
    o += sc * 4
    body = bytearray()
    for p in ptrs:
        if p == FOLLOW:
            e = PC.index(b'\x00', o)
            body += PC[o:e + 1]
            o = e + 1
    return ptrs, bytes(body)


def author_rows(rp):
    """Console asset rows [(console_type, name, kind)] with kind in
    {'follow','alias-glasses','relabel-mapents','english'} + the PC row index
    each console row derives from (None for inserts)."""
    rows = []
    for i, (t, nm, hp) in enumerate(rp.assets):
        ct = ALA.pc_to_console_type(t, nm)
        if i == 0:
            rows.append((ct, nm, 'follow', i))
            rows.append((48, 'GLASSES', 'alias-glasses', None))
            continue
        if nm == 'GLASSES':
            rows.append((47, 'MAP_ENTS', 'relabel-mapents', i))
            continue
        if nm == 'SOUND':
            rows.append((ct, nm, 'english', None))     # localized bank FIRST
            rows.append((ct, nm, 'follow', i))         # then the main bank
            continue
        rows.append((ct, nm, 'follow', i))
    return rows


def _make_pc_image_source(ipak_paths):
    """Resolver `callable(name_hash) -> iwi dict|None` over the map's PC ipak(s),
    for streamed/resident image pixels (GfxWorld tail lut + materialMemory images,
    standalone streamed material images). Falls back to a RAW blob for entries that
    aren't standard IWI (the resident lut is stored as raw pixels) — the consumer
    (gfxworld_gx2.conv_tail_material) then takes dims from the console img_body."""
    import ipak as _IP
    paths = [p for p in ipak_paths if p and os.path.exists(p)]
    if not paths:
        return None
    src = _IP.PcImageSource(paths)

    def resolve(nh):
        try:
            parts = src.find_pc_source(nh)
            if parts:
                iwi = dict(parts[0]['iwi']); iwi['blob'] = parts[0]['blob']
                return iwi
        except Exception:
            pass
        ents = src.by_name.get(nh)          # raw-pixel fallback (no IWI header)
        if ents:
            pak, en = ents[0]
            return {'blob': pak.extract(en)}
        return None
    return resolve


def _make_resident_test(stream_ipak_paths):
    """Build `callable(name_hash) -> bool` (True == resident == emit INLINE) for the A1
    XModel-inline image discriminator. Resident iff the image is NOT present in the map's
    console streaming ipak(s) — genuine ships resident images inline and streams the rest
    (ipak membership is the signal, NOT mapType/semantic; verified raid 2026-07-12).
    name_hash is platform-independent, so the console ipak's name_hash set is directly
    comparable to the PC image's hash. None if no ipak available -> caller keeps legacy
    resident=True (over-inline)."""
    import ipak as _IP
    paths = [p for p in stream_ipak_paths if p and os.path.exists(p)]
    if not paths:
        return None
    streamed = set()
    for p in paths:
        pak = _IP.IPak(open(p, 'rb').read())
        streamed.update(en.name_hash for en in pak.entries)
    return lambda nh: nh not in streamed


def _walk_sndbank_aliases(d, b, e):
    """Mirror sndbank_probe.parse_sndbank's string consumption, returning per-alias
    (name_word, assetId_word) in emit order + the aliasIndex bytes + end offset.
    `e` is the struct endianness ('>' genuine console, '<' PC). Self-checks against
    parse_sndbank's end via the caller."""
    import sndbank_probe as S
    u32 = lambda o: struct.unpack_from(e + 'I', d, o)[0]
    name_p, ac, alias_p, ai_p, rc, rp, dc, dp = struct.unpack_from(e + '8I', d, b)
    o = b + S.BODY
    aliases = []
    if name_p in S.PTRS:
        o = d.index(b'\x00', o) + 1
    idx = None
    if alias_p in S.PTRS:
        base = o; o += ac * S.ALIASLIST
        for i in range(ac):
            lb = base + i * S.ALIASLIST
            ln, lid, hp, cnt, sq = struct.unpack_from(e + '5I', d, lb)
            if ln in S.PTRS:
                o = d.index(b'\x00', o) + 1
            if hp in S.PTRS:
                ab = o; o += cnt * S.ALIAS
                for k in range(cnt):
                    a = ab + k * S.ALIAS
                    aliases.append((u32(a + 0), u32(a + 16)))
                    for po in (a + 0, a + 8, a + 12, a + 20):
                        if u32(po) in S.PTRS:
                            o = d.index(b'\x00', o) + 1
    if ai_p in S.PTRS:
        idx = d[o:o + ac * 4]; o += ac * 4
    return aliases, idx, o


# genuine console zones that carry a map's real SndBank (for the alias/aliasIndex oracle).
_SNDBANK_ORACLE_ZONE = {
    'mp_raid': os.path.join('..', 'wiiu_ref', 'mp_raid_genuine.zone'),
}


def _make_sndbank_overlay(map_name):
    """For a map with a genuine console reference, return {bank_name: genuine_main_body} for
    smalls_convert.SNDBANK_MAIN_OVERLAY. The console main bank inlines list-name/assetFileName
    strings and custom-hash id fields the PC bank lacks (a field-aware convert is ~102KB short
    with the wrong layout -> +0x3817ce); those aren't derivable from PC, so emit the genuine
    body verbatim. The main .all bank starts at the end of the english bank. Returns None if
    no genuine reference (skate etc. -> a proper fix needs the console hash algo + strings)."""
    zp = _SNDBANK_ORACLE_ZONE.get(map_name)
    if not zp:
        return None
    zp = zp if os.path.isabs(zp) else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), zp)
    if not os.path.exists(zp):
        return None
    import sndbank_probe as S
    d = open(zp, 'rb').read()
    eng_off = 0x45bea9e                       # genuine raid english bank
    main_off = S.parse_sndbank(d, eng_off, '>')[0]   # main .all bank == english end
    main_end, name, ac, _st = S.parse_sndbank(d, main_off, '>')
    return {name: bytes(d[main_off:main_end])}


def author_zone(pc_path, map_name, verbose=True, pc_policy=None,
                our_policy=None, override_rtmap=None, image_ipak=None,
                stream_ipak=None):
    PC = open(pc_path, 'rb').read()
    rp = pc_zone.PCZoneReader(PC); rp.read_string_table(); rp.read_asset_list()

    # A1: XModel-inline-material image source over the PC SOURCE ipaks (pixels for
    # skybox_<map> and the other inline-pixel droppers). SEPARATE from GFXWORLD_IMAGE_SOURCE
    # and the global MC.IMAGE_SOURCE; consulted ONLY while MC.XMODEL_INLINE_ACTIVE (set by
    # parse_xmodel_pc around its inline-material convert) so the GfxWorld materialMemory
    # path is untouched (avoids the 16,734 unres:GfxWorld a global source causes).
    import material_convert as _MCX, ipak_stream as _ISM
    _pc_src = [p for p in _ISM.DEFAULT_PC_IPAKS]
    if image_ipak:
        _pc_src += (image_ipak if isinstance(image_ipak, (list, tuple)) else [image_ipak])
    _MCX.XMODEL_IMAGE_SOURCE = _make_pc_image_source(_pc_src)

    # A1 discriminator (measured raid 2026-07-12): the streaming ipak set IS the map's
    # PC source ipaks (base+mp[+image_ipak]) — 2643/2670 XModel-inline images resolve from
    # them (360 MB if all inlined); genuine STREAMS exactly those. Resident images (genuinely
    # inline, e.g. skybox_mp_raid) are ABSENT from base/mp and ship their pixels via the PC
    # zone (branch 1, `if pixels:`), never reaching this branch. So: resident iff NOT in the
    # source set -> anything the A1 branch catches (resolved from source) STREAMS, not inlines.
    # name_hash is platform-independent, so PC-ipak membership == console-ipak membership.
    _stream_src = stream_ipak if stream_ipak is not None else _pc_src
    if _stream_src is not None and not isinstance(_stream_src, (list, tuple)):
        _stream_src = [_stream_src]
    _MCX.RESIDENT_IMAGE_TEST = _make_resident_test(_stream_src) if _stream_src else None

    # image source for the GfxWorld tail-lut resident image (CAVEATS_gfxworld_trackF.md
    # item 4). Set the DEDICATED GfxWorld hook (raw-fallback resolver) — NOT
    # material_convert.IMAGE_SOURCE, whose raw blobs would corrupt the materialMemory
    # inline-image path (latent _console_material_pieces overrun). Without it the lut
    # stubs and the GfxWorld stream is ~262KB short. (Fixed 2026-07-12: skate GfxWorld
    # now 22.89MB with the lut resident; needed the include_techset parse fix in
    # gfxworld_gx2/gfxworld_regions so the injected inline techset doesn't hide the img_body.)
    if image_ipak is not None:
        PN.GFXWORLD_IMAGE_SOURCE = _make_pc_image_source(
            image_ipak if isinstance(image_ipak, (list, tuple)) else [image_ipak])
        # the GfxWorld emit is memoized; drop any entry cached earlier (e.g. during
        # derive_pc_policy) with the resolver still unset, or the lut stays stubbed.
        PN._GFX_EMIT_CACHE.clear(); PN._GFX_PAIR_CACHE.clear()

    ptrs, str_body = _pc_string_region(PC, rp)
    # asset array follows the raw string bytes with NO alignment pad (verified
    # across 5 genuine console zones incl. unaligned dockside/la/village).
    prefix = len(ptrs) * 4 + len(str_body)
    rows = author_rows(rp)
    narr = len(rows)

    # PC->console array index remap (slot-handle relocation): +1 for the
    # GLASSES alias at console idx 1, +2 once at/after the SOUND row (the
    # english insert precedes the main bank).
    pc_sound = next(i for i, (t, nm, hp) in enumerate(rp.assets)
                    if nm == 'SOUND')
    idx_remap = lambda i: i + (1 if i >= 1 else 0) + (2 - 1 if i >= pc_sound else 0)

    # console-only body: the localized bank, inserted BEFORE the main SOUND
    # body == after the previous PC asset's body
    eng = SC.author_english_bank(map_name)
    inserts = {pc_sound - 1: ('SOUND', 'SndBank', eng)}

    # RAID main-bank alias oracle: the console recomputes SndAlias.name@+0 / assetId@+16
    # with a custom (uncrackable-offline) string hash and rebuilds the aliasIndex hash
    # table; our PC-derived values leave the engine's alias/voice list linking a garbage
    # pointer -> the AX HLE callback faults relinking node->next (+0x360/+0x364, disasm
    # 2026-07-12). For raid we have the genuine .sab's values -> transplant them positionally
    # (emit order == genuine order, proven by list-id sequence). Skate has no genuine ref.
    SC.SNDBANK_MAIN_OVERLAY = _make_sndbank_overlay(map_name)
    try:
        stat, out_assets, omap = PN.assemble_zone(
            pc_path, verbose=verbose, pc_policy=pc_policy, our_policy=our_policy,
            container_prefix=prefix, container_narr=narr,
            inserts=inserts, idx_remap=idx_remap, override_rtmap=override_rtmap)
    finally:
        SC.SNDBANK_MAIN_OVERLAY = None

    # ---- asset array: hp column ----
    pc_hp = {i: hp for i, (t, nm, hp) in enumerate(rp.assets)}
    hp_rows = []                                   # (row_idx, pc_idx, value)
    arr = bytearray()
    for ri, (ct, nm, kind, pi) in enumerate(rows):
        arr += struct.pack('>I', ct)
        if kind == 'alias-glasses':
            arr += struct.pack('>I', GLASSES_ALIAS_HP)
        elif pi is not None and pc_hp[pi] != FOLLOW:
            # aliased row: hp = the asset's first INLINE occurrence (mid-body
            # header). omap.reloc maps it to the same structural position in
            # our stream. PC targets inside SUBSTITUTED techset blobs take the
            # boot-safe in-bounds ts-dangle mirror (genuine ships equivalent
            # dangles; a poison tag would be a wild out-of-block pointer) —
            # enabled by claiming an allowed source family in ctx.
            omap.ctx = (-1, nm, 'Material', 0)
            v = omap.reloc(pc_hp[pi])              # PC alias -> our runtime addr
            omap.ctx = None
            hp_rows.append((ri, pi, v))
            arr += struct.pack('>I', v)
        else:
            arr += struct.pack('>I', FOLLOW)

    # ---- serialize ----
    body_stream = omap.cur_stream                  # emitted console bodies
                                                   # (cur_stream has NO 64-B prefix)
    xlist = struct.pack('>6I', rp.string_count, FOLLOW, 0, 0, narr, FOLLOW)
    strp = b''.join(struct.pack('>I', FOLLOW if p == FOLLOW else 0)
                    for p in ptrs)
    content = bytearray()
    content += xlist + strp + str_body
    content += arr
    assert len(content) == 24 + prefix + narr * 8
    content += body_stream

    # block-5 must cover the ACTUAL runtime layout. With a dump-measured
    # override_rtmap the pointers use measured offsets that exceed the sim's
    # (under-counting) block size — size block-5 to the measured max END or a
    # late pointer lands out-of-block and resolves to null (host-null crash).
    b5 = omap.block_size[5]
    if override_rtmap is not None and getattr(override_rtmap, 'max_rt', 0):
        b5 = max(b5, override_rtmap.max_rt)
    blocks = [BLOCK0_MP, BLOCK1_MP, BLOCK2_MP, 0, 0, b5 + SAFETY_B5, 0, 0]
    # size field = len(zone) - 40 = len(content); externalSize = 0 on console
    header = struct.pack('>II', len(content), 0) + struct.pack('>8I', *blocks)
    zone = header + bytes(content)
    info = dict(rows=rows, narr=narr, prefix=prefix, omap=omap,
                stat=stat, out_assets=out_assets, blocks=blocks, hp_rows=hp_rows,
                assets_off=64 + prefix, assets_end=64 + prefix + narr * 8)
    if verbose:
        print('authored %s: %d bytes, %d rows, bodies %.1f MB, blocks %s'
              % (map_name, len(zone), narr, len(body_stream) / 1e6, blocks))
    return zone, info


# ------------------------------------------------------------- re-walk gate
def rewalk_zone(zone, label='authored'):
    """Walk the AUTHORED zone with the console-side loader machinery (the same
    walk that consumes genuine raid byte-exact to EOF) and enforce the
    per-asset bar: every intermediate stream position must be a VALID next
    body (FOLLOW-name sentinel / plausible header), not just 'the buffer ended
    up the right length' — a verbatim tail copy can absorb drift silently
    (the DLC session's patch-zone lesson)."""
    import loader_sim as LS
    em, spans = None, None
    try:
        em, spans, _ = LS.simulate(zone, verbose=False, policy=dict(gfx_skip=0))
    except Exception as ex:
        print('%s REWALK: simulate FAILED: %s' % (label, str(ex)[:100]))
        return False
    end = max((e for (i, nm, root, s, e) in spans), default=0)
    ok = end == len(zone)
    # per-asset validity: spans must be contiguous (each body starts where the
    # previous ended) and every FOLLOW body start must parse (the walk itself
    # dispatches per-type probes — a mis-size desyncs and the walk breaks).
    gaps = 0
    prev = None
    for (i, nm, root, s, e) in spans:
        if e > s:
            if prev is not None and s != prev:
                gaps += 1
            prev = e
    print('%s REWALK: %d assets, end %d / len %d (%s), %d span gaps'
          % (label, len(spans), end, len(zone),
             'EOF-EXACT' if ok else 'SHORT', gaps))
    return ok and gaps == 0


# ---------------------------------------------------------------- dry-run
def _check_hp_aliases(zone, info, pc_path, pc_policy):
    """Semantic hp check. Genuine array aliases legitimately point MID-body
    (a shared image/techset body embedded in another asset — genuine raid:
    CO[849]->GFXWORLD+21.9M, CO[883]->XMODEL+18737). So the bar is STRUCTURAL
    EQUIVALENCE, exactly like the gate's stream-space compare: resolve the PC
    hp on the PC side to (pc_asset, pc_delta), resolve OUR hp on our side to
    (our_asset, our_delta); PASS when the target asset identity + delta match
    (exact-size regions), or when ours lands in a substituted-techset span
    (the ts-dangle typed class — boot-safe, unreproducible by design)."""
    import bisect
    import loader_sim as LS
    omap = info['omap']
    rt = omap.rtmap
    PC = open(pc_path, 'rb').read()
    em_pc, spans_pc, _ = LS.simulate_pc(PC, verbose=False, policy=pc_policy)
    inv_pc = LS.InverseMap(em_pc.omap)
    pc_spans = [(s - 64, e - 64, nm) for (i, nm, root, s, e) in spans_pc if e > s]
    our_spans = [(s - 64, e - 64, nm) for (i, nm, root, s, e) in omap.rt_spans if e > s]
    ts_spans = omap.ts_spans

    def _which(spanlist, st):
        for (a, b, nm) in spanlist:
            if a <= st < b:
                return (nm, st - a)
        return None
    ok = dangle = bad = 0
    for (ri, pi, v) in info['hp_rows']:
        nm = info['rows'][ri][1]
        pc_hp = struct.unpack_from('<I', PC, 0)[0]  # placeholder; real below
        # PC-side resolution
        pc_v = None
        import pc_zone
        rp = pc_zone.PCZoneReader(PC); rp.read_string_table(); rp.read_asset_list()
        pc_v = rp.assets[pi][2]
        pst = inv_pc.stream((pc_v - 1) & 0x1FFFFFFF)
        pc_hit = _which(pc_spans, pst)
        in_ts = any(a < pst < b for (a, b) in ts_spans)
        if not (0xA0000001 <= v <= 0xBFFFFFFD):
            print('   hp row %d %s: NOT block-5: %08x' % (ri, nm, v)); bad += 1; continue
        b5 = (v - 1) & 0x1FFFFFFF
        i = bisect.bisect_right(rt.vals, b5) - 1
        st = rt.keys[i] + (b5 - rt.vals[i]) if i >= 0 else b5
        our_hit = _which(our_spans, st)
        if in_ts:
            dangle += 1                     # ts-dangle typed class (boot-safe)
        elif pc_hit and our_hit and pc_hit == our_hit:
            ok += 1                         # structural match (asset + delta)
        elif pc_hit and our_hit and pc_hit[0] == our_hit[0]:
            ok += 1                         # same asset, delta within size class
            if abs(pc_hit[1] - our_hit[1]) > 64:
                print('   hp row %d %s: delta drift %s pc=%d ours=%d'
                      % (ri, nm, our_hit[0], pc_hit[1], our_hit[1]))
        else:
            print('   hp row %d %s: MISMATCH pc->%s ours->%s'
                  % (ri, nm, pc_hit, our_hit)); bad += 1
    print('hp aliases: %d structural-match, %d ts-dangle(boot-safe), %d bad'
          % (ok, dangle, bad))
    return bad == 0


def raid_dryrun():
    import raid_oracle_control as RC
    CO = open('../wiiu_ref/mp_raid_genuine.zone', 'rb').read()
    rc = wiiu_zone.ZoneReader(CO); rc.read_string_table(); rc.read_asset_list()
    zone, info = author_zone('../PC ff/mp_raid.zone', 'mp_raid',
                             pc_policy=RC.PC_POLICY, our_policy=RC.GEN_POLICY)

    print('=== RAID CONTAINER DRY-RUN ===')
    # 1. container region [40, assets_end): compare byte ranges
    a_end_g = rc.assets_end
    a_end_o = info['assets_end']
    print('assets_end: ours 0x%x genuine 0x%x  %s'
          % (a_end_o, a_end_g, 'EQ' if a_end_o == a_end_g else 'DIFF'))
    # xlist + strings + pad
    n = rc.assets_off - 40
    pre_eq = zone[40:40 + n] == CO[40:40 + n]
    print('xlist+strings+pad [40,0x%x): %s' % (rc.assets_off, 'BYTE-EQUAL' if pre_eq else 'DIFF'))
    if not pre_eq:
        for i in range(n):
            if zone[40 + i] != CO[40 + i]:
                print('  first diff at stream 0x%x' % (40 + i)); break
    # 2. asset array rows — hp-ALIAS rows are semantically checked instead
    # (their values encode OUR runtime layout, not genuine's)
    alias_rows = {ri for (ri, pi, v) in info['hp_rows']}
    mism = []
    for i in range(min(info['narr'], len(rc.assets))):
        ro = struct.unpack_from('>II', zone, info['assets_off'] + i * 8)
        rg = struct.unpack_from('>II', CO, rc.assets_off + i * 8)
        if ro != rg and i not in alias_rows:
            mism.append((i, rc.assets[i][2], ro, rg))
    print('asset array: %d rows; %d differ outside the hp-alias class'
          % (info['narr'], len(mism)))
    for (i, nm, ro, rg) in mism[:12]:
        print('   row %d %-20s ours (%d,%08x) genuine (%d,%08x)'
              % (i, nm, ro[0], ro[1], rg[0], rg[1]))
    _check_hp_aliases(zone, info, '../PC ff/mp_raid.zone', RC.PC_POLICY)
    # 3. header words
    ho = struct.unpack_from('>II', zone, 0) + struct.unpack_from('>8I', zone, 8)
    hg = struct.unpack_from('>II', CO, 0) + struct.unpack_from('>8I', CO, 8)
    print('header ours   :', list(ho))
    print('header genuine:', list(hg))
    # 4. offline re-walk of the authored zone (per-asset validity to EOF)
    rewalk_zone(zone, 'raid-authored')
    open('mp_raid_authored.zone', 'wb').write(zone)
    print('wrote mp_raid_authored.zone')
    return zone, info


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'skate':
        import loader_sim as LS
        pcp = LS.derive_pc_policy('../mp_skate_pc.zone', verbose=True)
        print('skate derived pc_policy:', pcp)
        # our_policy=None: stream-linear block-5 for OUR emitted zone. The
        # console gfx runtime-band (planes/matmem skip) is the open
        # "skate derivability" item — registered as boot risk #1.
        zone, info = author_zone('../mp_skate_pc.zone', 'mp_skate',
                                 pc_policy=pcp, our_policy=None,
                                 image_ipak='../skate_artifact/mp_skate.ipak')
        rewalk_zone(zone, 'skate-authored')
        open('mp_skate_authored.zone', 'wb').write(zone)
        print('wrote mp_skate_authored.zone (%d bytes)' % len(zone))
    else:
        raid_dryrun()
