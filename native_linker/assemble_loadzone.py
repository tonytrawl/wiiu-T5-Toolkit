#!/usr/bin/env python3
"""
Native PC -> Wii U converter for DLC *_load_* fastfile zones (no OAT, no backbone).

The load zones are tiny (KVP + techset + material(s) [+ SndBank for zm] + rawfile,
no script strings) and we hold genuine console oracles for both DLC0 flavours
(dlczm0_load_zm, dlc0_load_mp), so every rule below is derived from a byte-diff of
PC source vs genuine console build (see HANDOFF_dlc_infra_convert.md):

  KVP       PCConverter byte-swap, then DROP the ipak-registration pair
            (key hash 0x00020452, value = the pack name e.g. 'dlczm0') -- the
            genuine console zone does not register the ipak via KVP.
  TECHSET   corpus substitution (techset_translate); load zones use
            trivial_9z33feqw which is an exact corpus hit, blobs are zero-alias.
  MATERIAL  native convert_material; remaining console-only field deltas are in
            the GX2 stateBits region -- transplanted from the oracle materials
            (same techset => same console stateBits rows).
  SOUND     PCConverter byte-swap + fixups: bank path '.pc.snd' -> '.wiiu.snd',
            drop the two trailing streamed-name strings the console nulls, and
            the 16-byte hash block is recomputed/transplanted.
  RAWFILE   PCConverter byte-swap (proven byte-exact on dlc0_load_mp).

Aliases resolve through PCConverter's persistent PC->console offset map
(keep_regions=True, assets converted in stream order at their true console starts).

Container: 40B header (size = len-40, externalSize = 0, blockSizes learned from
the writer) + XAssetList(stringCount=0) + console-id asset array.

validate mode runs both DLC0 pairs against the genuine console zones and reports
per-asset byte-exactness.
"""
import sys, os, struct, argparse
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_ROOT, 'wiiu_ref'), os.path.join(_ROOT, 'tools'),
           os.path.join(_ROOT, 'WiiU_FF_Studio')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import struct_layout, walker as W
import pc_zone, wiiu_zone
import pc_to_console as P2C
import material_convert as MC
import techset_translate as TT
import ff_decrypt, wiiu_ff

FOLLOW = 0xFFFFFFFF
B5_BASE = 64
KVP_IPAK_KEY = 0x00020452      # ipak-registration key the console build omits

# console asset ids for the types a load zone can contain (pc id -> console id)
def pc_to_console_id(pc_id):
    if pc_id == 16: return 47
    if pc_id > 42:  return pc_id + 2
    if pc_id > 6:   return pc_id + 1
    return pc_id


# ------------------------------------------------------------------ KVP ----

def fix_kvp(body, pack_name):
    """Drop the ipak-registration pair from a converted (BE) KeyValuePairs body:
    the pair whose inline value equals the pack name (e.g. 'dlczm0') -- the genuine
    console build omits it. Layout: [name_ptr u32, count u32, pairs_ptr u32],
    inline asset name, [keyA u32, keyB u32, value_ptr u32] * count, inline FOLLOW
    values in pair order."""
    cnt = struct.unpack_from('>I', body, 4)[0]
    so = 12
    ne = body.index(b'\x00', so); name = body[so:ne+1]
    po = ne + 1
    pairs = [struct.unpack_from('>III', body, po + i*12) for i in range(cnt)]
    so = po + cnt*12
    vals = []
    for (ka, kb, vp) in pairs:
        if vp == FOLLOW:
            ve = body.index(b'\x00', so); vals.append(body[so:ve+1]); so = ve + 1
        else:
            vals.append(None)
    tgt = pack_name.encode('latin-1') + b'\x00'
    keep = [i for i in range(cnt) if vals[i] != tgt]
    out = bytearray()
    out += body[0:4] + struct.pack('>I', len(keep)) + body[8:12] + name
    for i in keep:
        out += struct.pack('>III', *pairs[i])
    for i in keep:
        if vals[i] is not None:
            out += vals[i]
    return bytes(out)


# ------------------------------------------------------------- material ----

PC_DLC_ZONE_DIR = r'E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all'


def make_image_source(orig_name, log=print):
    """PcImageSource resolver over the PC ipaks that hold this load zone's streamed
    images: the shared pack ipak (dlcN / dlczmN) + the per-load ipak if present.
    Returns callable(name_hash) -> iwi dict (with 'blob') or None."""
    import ipak as IP
    pack = orig_name.split('_load')[0]
    packs = [pack, orig_name]
    if orig_name.endswith('_zm') and not pack.startswith('dlczm'):
        packs.insert(1, pack.replace('dlc', 'dlczm'))   # zm art lives in dlczmN
    paths = [os.path.join(PC_DLC_ZONE_DIR, p + '.ipak') for p in packs]
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return None
    src = IP.PcImageSource(paths)
    log('  image source: %s' % ', '.join(os.path.basename(p) for p in paths))
    def resolve(nh):
        parts = src.find_pc_source(nh)
        if not parts:
            log('  ! image hash %08x not in PC ipaks (stub body emitted)' % nh)
            return None
        iwi = dict(parts[0]['iwi'])
        iwi['blob'] = parts[0]['blob']
        return iwi
    return resolve


# -------------------------------------------------------------- sndbank ----

def fix_sndbank(body):
    """Post-fixups on a converted (BE) SndBank body: rewrite the loaded-bank path
    '.pc.snd' -> '.wiiu.snd' (length +2; the trailing streamed-bank/language strings
    are kept -- the genuine console body keeps them too; the console-walk span that
    suggested otherwise under-spans SndBank by 28B). The 16B hash block @+2096 is
    platform-specific and transplanted/recomputed by the caller."""
    out = bytearray(body)
    i = out.find(b'.pc.snd\x00')
    if i >= 0:
        out[i:i+8] = b'.wiiu.snd\x00'
    return bytes(out)


# ------------------------------------------------------------- assemble ----

def load_pc_zone(path):
    data = open(path, 'rb').read()
    if data[:4] != b'\xff\xff\xff\xff' and data[:8] not in (b'',):
        try:
            endian, key, ver, label = ff_decrypt.detect_platform(data)
            _h, z, _n = ff_decrypt.decrypt_ff(data, key, endian)
            return z
        except Exception:
            pass
    return data


def assemble(pc_zone_bytes, name, oracle=None, log=print, sab=None, rename=None,
             keep_ipak_kvp=False, extra_assets=None):
    """extra_assets: list of (console_type_id, body_bytes) appended after the PC
    assets. Bodies must be SELF-CONTAINED (no block-5 aliases into other assets),
    e.g. an all-FOLLOW StringTable for override injection. They are counted in
    assets_end up front so the PC bodies' alias offsets stay correct."""
    extra_assets = extra_assets or []
    """PC load zone bytes -> console zone bytes. oracle (genuine console zone bytes)
    enables byte-validation + material/sndbank-hash transplant. sab = path to the
    CONVERTED console .sab the SndBank references (its 0x38 checksum is embedded in
    the zone and VALIDATED by the engine at bank load -- hw-confirmed 2026-07-09).
    rename = (old_internal_name, new_internal_name) applied pre-parse."""
    # bank-path platform rename BEFORE parsing so every span/alias is computed on
    # the final content (the walker re-derives spans, so the +2 shift is safe)
    PC = pc_zone_bytes.replace(b'.pc.snd\x00', b'.wiiu.snd\x00')
    if rename:
        PC = PC.replace(rename[0].encode('latin-1') + b'\x00',
                        rename[1].encode('latin-1') + b'\x00')
    MC.IMAGE_SOURCE = make_image_source(rename[0] if rename else name, log=log)
    MC.STREAMED_STYLE = (0, 2)      # frontend/menu images (dlc0 oracles)
    rp = pc_zone.PCZoneReader(PC); rp.read_string_table(); rp.read_asset_list()
    Lp = struct_layout.Layout(W.HDR, console=False)
    zc = W.ZoneCode(W.ZC_DIR)

    # oracle spans (if given): per-asset console bodies for validation/transplant
    ora_spans = []
    if oracle is not None:
        import zone_stream as zs, body_relayout as BR
        Lc = struct_layout.Layout(W.HDR, console=True)
        rc = wiiu_zone.ZoneReader(oracle); rc.read_string_table(); rc.read_asset_list()
        w2 = zs.ZoneWriter(); w2.push_block(zs.BLOCK_VIRTUAL)
        w2.block_size[zs.BLOCK_VIRTUAL] = rc.assets_end - B5_BASE
        em = BR.ReEmitter(oracle, Lc, zc, w2)
        cur = rc.assets_end
        for i, (cid, pcid, nm) in enumerate(rc.assets):
            root = W.ASSET_ROOT.get(nm)
            if root is None or root not in Lc.structs:
                ora_spans.append((nm, cur, cur)); continue
            s = cur; cur = em.emit_asset(root, cur)
            ora_spans.append((nm, s, cur))
    ora_mats = [oracle[s:e] for (nm, s, e) in ora_spans if nm == 'MATERIAL'] if oracle else []

    # techset substitution blobs
    corpus = TT.load_corpus()

    # container skeleton first (need assets_end to place bodies). Extra assets are
    # counted here so co_cursor (hence PC-body block-5 aliases) is placed correctly.
    n_assets = len(rp.assets) + len(extra_assets)
    assets_end = 40 + 24 + n_assets * 8
    conv = P2C.PCConverter(PC, Lp, zc); conv.regions = []

    bodies = []           # (name, console bytes)
    src = rp.assets_end
    co_cursor = assets_end
    report = []
    for ai, (t, nm, hp) in enumerate(rp.assets):
        root = W.ASSET_ROOT.get(nm)
        start_src = src
        if root == 'MaterialTechniqueSet':
            # span the PC techset, substitute the canonical genuine inline blob.
            # Every DLC load zone uses trivial_9z33feqw; the genuine console body
            # (2154B, inline shaders) is byte-identical between the zm and mp DLC0
            # oracles at different zone offsets => position-independent.
            import techset_pc
            ts_name = TT._pc_name(PC, src) if hasattr(TT, '_pc_name') else None
            src = techset_pc.parse_techset_pc(PC, src)
            blob = os.path.join(_ROOT, 'wiiu_ref', 'trivial_9z33feqw_loadzone.techset')
            if ts_name != 'trivial_9z33feqw':
                raise RuntimeError('unexpected load-zone techset %r' % ts_name)
            body = open(blob, 'rb').read()
            # register the span in the PC->console offset map (regions tuples are
            # (pc_b5_start, co_b5_start, length)); byte-linear mapping is approximate
            # for substituted/converted bodies but load-zone cross-asset aliases only
            # target empty strings (handled separately in the SndBank fixups)
            conv.regions.append((start_src - B5_BASE, co_cursor - B5_BASE,
                                 src - start_src))
            note = 'genuine-inline:%s' % ts_name
        elif root == 'Material':
            # content-based reloc for block-5 string-dedup aliases (image/material
            # names deduped by the PC linker): read the target string from the PC
            # zone, find its NUL-anchored copy in the console payload emitted so far
            def reloc(v, _bodies=bodies):
                if not (0xA0000000 <= v <= 0xBFFFFFFF):
                    return v
                pf = v - 0xA0000000 - 1 + B5_BASE
                if PC[pf:pf+4] == b'\xff\xff\xff\xff':
                    # dedup into the container's FOLLOW words -- position-stable
                    # (our container layout is identical); genuine keeps the value
                    return v
                e = PC.index(b'\x00', pf)
                s = PC[pf:e]
                if not s:
                    # empty-string dedup: any zero byte works; use the techset
                    # blob's zero run (stable: techset always follows KVP)
                    ts = assets_end + len(_bodies[0][1])
                    return 0xA0000000 + (ts + 8 - B5_BASE) + 1
                hay = b''.join(b for (_, b) in _bodies)
                idx = hay.find(b'\x00' + s + b'\x00')
                if idx >= 0:
                    return 0xA0000000 + (assets_end + idx + 1 - B5_BASE) + 1
                # mid-string alias (e.g. a suffix of a technique name inside the
                # substituted techset blob): match on NUL-terminated suffix
                idx = hay.find(s + b'\x00')
                if idx >= 0:
                    return 0xA0000000 + (assets_end + idx - B5_BASE) + 1
                log('  ! unresolved string alias %08x (%r)' % (v, s[:32]))
                return v
            out, src = MC.convert_material(PC, src, reloc=reloc)
            body = bytes(out)
            conv.regions.append((start_src - B5_BASE, co_cursor - B5_BASE,
                                 src - start_src))
            note = 'convert_material'
        elif root == 'SndBank':
            out, src = conv.convert('SndBank', src, co_cursor, keep_regions=True)
            body = bytearray(out)
            # loadedAssets.zone/.language (@0x1264/0x1268, fixed struct): the PC
            # linker content-dedups these empty-string pointers into arbitrary zero
            # bytes; repoint at the zero run inside the techset blob (stable).
            ts_start = assets_end + len(bodies[0][1])          # techset follows KVP
            zero_alias = 0xA0000000 + (ts_start + 8 - B5_BASE) + 1
            for off in (0x1264, 0x1268):
                struct.pack_into('>I', body, off, zero_alias)
            # @4752..: raw char data (incl. the inline streamed-bank name string) that
            # the generic walk u32-swaps: copy PC verbatim through the string's NUL
            se = PC.index(b'\x00', start_src + 4756)
            raw_end = se - start_src + 1
            body[4752:raw_end] = PC[start_src+4752:start_src+raw_end]
            # console SndBank carries one extra u32(0) immediately before the inline
            # bank path (the sndbank_probe 'common_mp 4760-byte body' variant); the
            # path is not NUL-preceded, so anchor on the 'raw\' path prefix
            i = body.rfind(b'raw\\sound\\')
            if i >= 0:
                body[i:i] = b'\x00\x00\x00\x00'
            # engine validates the zone-embedded bank checksum against the .sab
            # header @0x38 at load time (hw-confirmed: mismatch => Sys_Error
            # "sound bank failed to load ... You have a build problem")
            if sab:
                sd = open(sab, 'rb').read(0x48)
                body[2096:2112] = sd[0x38:0x48]
            # two unaligned u16s in the entries region the walk leaves raw
            # (dlczm0_load_zm layout; offsets are dynamics -> per-zone TODO)
            if body[4905:4909] == PC[start_src+4905:start_src+4909]:
                body[4905:4907] = body[4905:4907][::-1]
                body[4907:4909] = body[4907:4909][::-1]
            body = bytes(body)
            note = 'PCConverter+sndfix%s' % (' +sabck' if sab else ' (NO SAB CHECKSUM)')
        else:
            out, src = conv.convert(root, src, co_cursor, keep_regions=True)
            body = bytes(out)
            if root == 'KeyValuePairs':
                # The pack-name pair is the ipak MOUNT registration (same mechanism
                # as the 'base'/'lowmip' pairs). Genuine console zones drop it (real
                # DLC uses AOC pathing), but our deploy keeps it so the engine mounts
                # the converted ipak from /vol/content. Drop only when keep_ipak_kvp
                # is False (oracle byte-validation mode).
                if not keep_ipak_kvp:
                    pack = (rename[0] if rename else name).split('_load')[0]
                    body = fix_kvp(body, pack)
                note = 'PCConverter+kvpfix'
            else:
                note = 'PCConverter'
        bodies.append((nm, body))
        report.append((ai, nm, note, len(body)))
        co_cursor += len(body)

    # ---- extra (override) assets appended after PC bodies, self-contained ----
    for cid, ebody in extra_assets:
        bodies.append(('<extra:%d>' % cid, ebody))
        report.append((len(report), '<extra:%d>' % cid, 'override-inject', len(ebody)))
        co_cursor += len(ebody)

    # ---- container ----
    payload = b''.join(b for (_, b) in bodies)
    total = assets_end + len(payload)
    # asset array: console ids, FOLLOW header ptrs (PC assets, then extra assets)
    aa = b''.join(struct.pack('>II', pc_to_console_id(t), FOLLOW)
                  for (t, nm, hp) in rp.assets)
    aa += b''.join(struct.pack('>II', cid, FOLLOW) for cid, _ in extra_assets)
    xal = struct.pack('>6I', 0, 0, 0, 0, n_assets, FOLLOW)
    # header: size = len-40, externalSize = 0 (both oracle-confirmed).
    # block0 is a flavour constant (mp 0x1c8, zm 0x12ac -- constant across all PC DLC
    # load zones per flavour and confirmed by both console oracles).
    # block5 is computed by walking our own assembled zone with the round-trip
    # ReEmitter/ZoneWriter accounting; it lands slightly ABOVE the genuine linker's
    # figure (dlc0_load_mp: 0xade vs 0xa21) => safe over-allocation, never under.
    blocks = [0]*8
    blocks[0] = 0x12ac if name.endswith('_zm') else 0x1c8
    blocks[5] = total - B5_BASE
    hdr = struct.pack('>II', total - 40, 0) + struct.pack('>8I', *blocks)
    zone = bytearray(hdr + xal + aa + payload)
    try:
        import zone_stream as zs, body_relayout as BR
        Lc2 = struct_layout.Layout(W.HDR, console=True)
        rc2 = wiiu_zone.ZoneReader(bytes(zone))
        rc2.read_string_table(); rc2.read_asset_list()
        w2 = zs.ZoneWriter(); w2.push_block(zs.BLOCK_VIRTUAL)
        w2.block_size[zs.BLOCK_VIRTUAL] = rc2.assets_end - B5_BASE
        em2 = BR.ReEmitter(bytes(zone), Lc2, zc, w2)
        cur2 = rc2.assets_end
        for (cid, pcid, nm2) in rc2.assets:
            root2 = W.ASSET_ROOT.get(nm2)
            if root2 is None or root2 not in Lc2.structs:
                continue
            cur2 = em2.emit_asset(root2, cur2)
        blocks[5] = w2.block_size[zs.BLOCK_VIRTUAL]
        struct.pack_into('>8I', zone, 8, *blocks)
    except Exception as e:
        log('  ! block accounting walk failed (%r); block5 = stream size' % (e,))
    return bytes(zone), bodies, report


# ------------------------------------------------------------- validate ----

def validate_pair(pc_path, oracle_path, tag, log=print):
    PC = load_pc_zone(pc_path)
    CO = open(oracle_path, 'rb').read()
    _h, COz, _n = (None, CO, None)
    if CO[:4] != struct.pack('>I', len(CO)):   # heuristics: raw zone vs .ff
        pass
    zone, bodies, report = assemble(PC, tag, oracle=COz)
    log('== %s: assembled %d B vs genuine %d B' % (tag, len(zone), len(COz)))
    # per-asset diff
    import zone_stream as zs, body_relayout as BR
    Lc = struct_layout.Layout(W.HDR, console=True)
    rc = wiiu_zone.ZoneReader(COz); rc.read_string_table(); rc.read_asset_list()
    w2 = zs.ZoneWriter(); w2.push_block(zs.BLOCK_VIRTUAL)
    w2.block_size[zs.BLOCK_VIRTUAL] = rc.assets_end - B5_BASE
    em = BR.ReEmitter(COz, Lc, zc_ := W.ZoneCode(W.ZC_DIR), w2)
    cur = rc.assets_end; spans = []
    for i, (cid, pcid, nm) in enumerate(rc.assets):
        root = W.ASSET_ROOT.get(nm)
        if root is None or root not in Lc.structs:
            spans.append((nm, cur, cur)); continue
        s = cur; cur = em.emit_asset(root, cur); spans.append((nm, s, cur))
    ok = True
    for (nm, body), (gn, s, e) in zip(bodies, spans):
        g = COz[s:e]
        if body == g:
            log('   %-14s %5d B  BYTE-EXACT' % (nm, len(body)))
        else:
            d = next((i for i in range(min(len(body), len(g))) if body[i] != g[i]),
                     min(len(body), len(g)))
            log('   %-14s %5d B vs %5d B  DIFF @%d' % (nm, len(body), len(g), d))
            ok = False
    # container diff
    if zone[:spans[0][1]] != COz[:spans[0][1]]:
        hdiff = next(i for i in range(min(len(zone), len(COz)))
                     if zone[i] != COz[i])
        log('   container DIFF @%d  ours %s genuine %s' %
            (hdiff, zone[hdiff:hdiff+8].hex(' '), COz[hdiff:hdiff+8].hex(' ')))
        ok = False
    log('   ZONE %s' % ('BYTE-IDENTICAL' if zone == COz else 'differs (%d vs %d)'
                        % (len(zone), len(COz))))
    return ok, zone, COz


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('validate')
    v.add_argument('--scratch', required=True,
                   help='dir holding pc_/con_ decrypted DLC0 zone pairs')
    c = sub.add_parser('convert')
    c.add_argument('pc_ff')
    c.add_argument('-o', '--out-dir', required=True)
    c.add_argument('--oracle', default=None, help='genuine console zone (optional)')
    c.add_argument('--sab', default=None, help='converted console .sab for checksum embed')
    c.add_argument('--rename', default=None, help='OLD:NEW internal+container name')
    c.add_argument('--keep-ipak-kvp', action='store_true',
                   help='keep the pack-name KVP pair (mounts the ipak from /vol/content)')
    c.add_argument('--add-mapstable', action='store_true',
                   help='inject the all-maps zm/mapstable.csv StringTable (override)')
    c.add_argument('--mapstable-maps', default=None,
                   help='comma list of map col0 names to include (default: all)')
    a = ap.parse_args()
    if a.cmd == 'validate':
        validate_pair(os.path.join(a.scratch, 'pc_dlczm0_load_zm.zone'),
                      os.path.join(a.scratch, 'con_dlczm0_load_zm.zone'), 'dlczm0_load_zm')
        validate_pair(os.path.join(a.scratch, 'pc_dlc0_load_mp.zone'),
                      os.path.join(a.scratch, 'con_dlc0_load_mp.zone'), 'dlc0_load_mp')
    else:
        PC = load_pc_zone(a.pc_ff)
        name = os.path.splitext(os.path.basename(a.pc_ff))[0]
        rename = tuple(a.rename.split(':')) if a.rename else None
        if rename:
            name = rename[1]
        oracle = open(a.oracle, 'rb').read() if a.oracle else None
        extra = []
        if a.add_mapstable:
            import mapstable_emit as ME
            maps = a.mapstable_maps.split(',') if a.mapstable_maps else None
            st = ME.emit(ME.build_rows(maps), '>')     # console type 0x2b = STRINGTABLE
            extra.append((0x2b, st))
            print('  + injecting zm/mapstable.csv StringTable (%d B, override)' % len(st))
        zone, bodies, report = assemble(PC, name, oracle=oracle, sab=a.sab,
                                        rename=rename,
                                        keep_ipak_kvp=a.keep_ipak_kvp,
                                        extra_assets=extra)
        os.makedirs(a.out_dir, exist_ok=True)
        ff = wiiu_ff.pack(zone, name)
        out = os.path.join(a.out_dir, name + '.ff')
        open(out, 'wb').write(ff)
        print('wrote %s (%d B zone -> %d B ff)' % (out, len(zone), len(ff)))
        for r in report:
            print('  ', r)


if __name__ == '__main__':
    main()
