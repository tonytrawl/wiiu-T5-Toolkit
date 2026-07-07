#!/usr/bin/env python3
"""
gfxworld_remap.py — rewrite the genuine WiiU GfxWorld blob's alias pointers so it
can be transplanted into OUR converted zone via the OAT_GFXWORLD_FILE hook.

MODEL (proven in-session, 2026-07-05):
  The writer inlines the blob VERBATIM: body(1076) at our GfxWorld block base,
  then all dynamics contiguously (verified gap body->dynamics == 0, i.e. NO
  inline name/baseName between them; those are written as aliases like genuine).
  Therefore the transplant is a PURE CONSTANT SHIFT in block-5 space:
        DELTA = our_gfxworld_base - genuine_gfxworld_base
  The huge console gump/lightmap padding lives INSIDE the copied bytes, so it
  needs no simulation — every internal alias just gets +DELTA.

  Genuine GfxWorld base (block 5) = 0x2b733b4 ; its block span ends at the
  GameWorldMp base 0x40ae344. An alias target is classified by where it lands:

    B internal : target in [GEN_BASE, GEN_GWMP)   -> +DELTA           (bulk;
                 includes portal.cell backrefs, surf.material, inline images,
                 and the siege-skin tail self-aliases)
    C list     : target in the asset-list array   -> genuine entry index ->
                 (type,name) from the loader index log -> OUR list entry of the
                 same name (smdi.model -> XMODEL, mat.techset -> TECHSET)
    A external : target below GEN_BASE (a shared common_mp asset our lean zone
                 omitted) -> resolve to OUR same-named asset; if absent, rewrite
                 to a ",name" DB_Find reference so the loader binds it at runtime.

Inputs (relative to wiiu_ref/):
  mp_raid_genuine.zone, gfxworld_raid.blob,
  genuine_offsets.tsv (loader log: type,name,blk5off,index[,nested=-1]),
  our_offsets.tsv     (writer log: type,name,blk,off),
  ../mp_raid_rewrite.ff (our raw BE zone, for the asset list + block layout)

Output: gfxworld_raid_remapped.blob
Usage:  python gfxworld_remap.py [inventory|remap]
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiiu_zone

FOLLOW, INSERT = 0xFFFFFFFF, 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)

GEN_ZONE  = 'mp_raid_genuine.zone'
BLOB_IN   = 'gfxworld_raid.blob'
BLOB_OUT  = 'gfxworld_raid_remapped.blob'
GEN_TSV   = 'genuine_offsets.tsv'
OUR_TSV   = 'our_offsets.tsv'
OUR_ZONE  = '../mp_raid_rewrite.ff'

GEN_BODY_FILE = 0x2b7029d
GEN_END_FILE  = 0x40aa61d
GEN_BASE      = 0x2b733b4
GEN_GWMP_BASE = 0x40ae344
BODY_SIZE     = 1076
TAIL_SIZE     = 11085

# name string is this many bytes past the console asset struct (solved layouts)
NAME_OFF = {5: 244, 6: 104, 7: 136, 8: 328}   # XMODEL MATERIAL TECHSET IMAGE

def enc(off):    return 0xA0000000 + off + 1
def dec(v):      return (v - 1) & 0x1FFFFFFF
def is_alias(v): return 0xA0000000 <= v < 0xC0000000 and v not in PTRS


class Walk:
    """Structural walk over the genuine GfxWorld stream (FILE cursor only) that
    yields every alias-valued pointer field, so we can classify + rewrite it.
    Only genuine bytes are read; the destination shift is applied afterwards."""
    def __init__(self, data):
        self.d = data
        self.body = GEN_BODY_FILE
        self.f = GEN_BODY_FILE + BODY_SIZE
        self.slots = []           # (file_pos, kind)
        self.tail_file = None

    def u32(self, o): return struct.unpack_from('>I', self.d, o)[0]
    def u16(self, o): return struct.unpack_from('>H', self.d, o)[0]
    def g(self, off): return self.u32(self.body + off)

    def take(self, size): self.f += size; return self.f - size
    def cstr(self):
        e = self.d.index(b'\x00', self.f); self.f = e + 1
    def slot(self, fp, kind):
        if is_alias(self.u32(fp)): self.slots.append((fp, kind))

    def image(self, ctx):
        ib = self.take(328)
        self.slot(ib + 176, 'image.loadDef@' + ctx)
        if self.u32(ib + 320) in PTRS: self.cstr()
        else: self.slot(ib + 320, 'image.name@' + ctx)
        if self.u32(ib + 176) in PTRS and self.d[ib + 171] == 0:
            self.take(self.u32(ib + 160))
        return ib

    def material(self, ctx):
        b = self.take(104)
        tc, cc2, sbc = self.d[b+72], self.d[b+73], self.d[b+74]
        tsp, ttp = self.u32(b+80), self.u32(b+84)
        ctp, sbp, thermal = self.u32(b+88), self.u32(b+92), self.u32(b+96)
        if self.u32(b) in PTRS: self.cstr()
        else: self.slot(b, 'mat.name@' + ctx)
        if tsp in PTRS:
            import shader_probe
            end, _ = shader_probe.parse_techset(self.d, self.f)
            self.take(end - self.f)
        else:
            self.slot(b+80, 'mat.techset@' + ctx)
        if ttp in PTRS:
            defs = self.take(tc*16)
            for i in range(tc):
                ip = defs + i*16 + 12
                if self.u32(ip) in PTRS: self.image('mat')
                else: self.slot(ip, 'mat.texdef.image@' + ctx)
        if ctp in PTRS: self.take(cc2*32)
        if sbp in PTRS: self.take(sbc*8)
        if thermal in PTRS: self.material(ctx + '.thermal')
        else: self.slot(b+96, 'mat.thermal@' + ctx)
        return b

    def run(self):
        g = self.g
        self.slot(self.body + 36, 'body.skyBoxModel')
        if g(24) in PTRS: self.take(g(20)*48)
        if g(32) in PTRS: self.take(g(28)*4)
        if g(256) in PTRS: self.take(372)
        for co, po, sz in [(268,272,32),(276,280,16),(284,288,16),(292,296,24),
                           (300,304,16),(308,312,100),(316,320,16),(324,328,66),
                           (332,336,16),(340,344,36),(348,352,16)]:
            if g(po) in PTRS and g(co): self.take(g(co)*sz)
        if g(376) in PTRS: self.take(g(8)*20)
        if g(380) in PTRS: self.take(g(12)*2)

        cellCount = g(372)
        if g(392) in PTRS:
            cb = self.take(cellCount*48)
            for i in range(cellCount):
                co = cb + i*48
                atc, atp = self.u32(co+24), self.u32(co+28)
                pc_, pp_ = self.u32(co+32), self.u32(co+36)
                rc_, rp_ = self.d[co+40], self.u32(co+44)
                if atp in PTRS:
                    ab = self.take(atc*40)
                    for j in range(atc):
                        ao = ab + j*40; sic = self.u16(ao+30)
                        if self.u32(ao+32) in PTRS: self.take(sic*2)
                        else: self.slot(ao+32, 'aabb.smodelIndexes')
                if pp_ in PTRS:
                    pb = self.take(pc_*92)
                    for j in range(pc_):
                        po2 = pb + j*92
                        self.slot(po2 + 0, 'portal.cell')    # GfxCell* backref
                        vcnt = self.d[po2+40]
                        if self.u32(po2+36) in PTRS: self.take(vcnt*12)
                        else: self.slot(po2+36, 'portal.vertices')
                if rp_ in PTRS: self.take(rc_)

        D = 396
        rpc = g(D+4)
        if g(D+8) in PTRS:
            rb = self.take(rpc*76)
            for i in range(rpc):
                ro = rb + i*76
                if self.u32(ro+60) in PTRS: self.image('probe')
                else: self.slot(ro+60, 'probe.image')
                if self.u32(ro+64) in PTRS: self.take(self.u32(ro+68)*96)
        lmc = g(D+16)
        if g(D+20) in PTRS:
            lb = self.take(lmc*8)
            for i in range(lmc):
                for k in (0, 4):
                    if self.u32(lb+i*8+k) in PTRS: self.image('lightmap')
                    else: self.slot(lb+i*8+k, 'lightmap.image')
        if g(D+44) in PTRS: self.take(g(D+36))
        if g(D+76) in PTRS: self.take(g(D+68))
        if g(D+104) in PTRS: self.take(g(D+100)*2)

        L = 512
        mins = [self.u16(self.body+L+4+2*k) for k in range(3)]
        maxs = [self.u16(self.body+L+10+2*k) for k in range(3)]
        ra = g(L+20)
        if g(L+28) in PTRS: self.take((maxs[ra]-mins[ra]+1)*2)
        if g(L+36) in PTRS: self.take(g(L+32))
        if g(L+44) in PTRS: self.take(g(L+40)*4)
        if g(L+52) in PTRS: self.take(g(L+48)*168)
        if g(L+60) in PTRS: self.take(g(L+56)*54)
        if g(L+68) in PTRS: self.take(g(L+64)*40)

        if g(588) in PTRS: self.take(g(584)*64)
        mmc = g(620)
        if g(624) in PTRS:
            ab = self.take(mmc*8)
            for i in range(mmc):
                mp = ab + i*8
                if self.u32(mp) in PTRS: self.material('matmem')
                else: self.slot(mp, 'matmem.material')
        for so, tag in ((632, 'sun.sprite'), (636, 'sun.flare')):
            if g(so) in PTRS: self.material(tag)
            else: self.slot(self.body+so, tag)
        if g(788) in PTRS: self.image('outdoor')
        else: self.slot(self.body+788, 'outdoorImage')

        plc = g(264)
        if g(824) in PTRS:
            sb = self.take(plc*12)
            for i in range(plc):
                so = sb + i*12
                surfC, smodC = self.u16(so), self.u16(so+2)
                if self.u32(so+4) in PTRS: self.take(surfC*2)
                else: self.slot(so+4, 'shadowGeom.surf')
                if self.u32(so+8) in PTRS: self.take(smodC*2)
                else: self.slot(so+8, 'shadowGeom.smod')
        if g(828) in PTRS:
            rb = self.take(plc*8)
            for i in range(plc):
                hc = self.u32(rb+i*8)
                if self.u32(rb+i*8+4) in PTRS:
                    hb = self.take(hc*80)
                    for j in range(hc):
                        ho = hb + j*80
                        if self.u32(ho+76) in PTRS: self.take(self.u32(ho+72)*20)

        dp = 832
        smodelCount = g(dp); staticSurfaceCount = g(dp+4)
        smVis = g(dp+40); surfaceCount = g(16)
        if g(dp+108) in PTRS: self.take(smVis)
        if g(dp+80) in PTRS: self.take(staticSurfaceCount*2)
        if g(dp+84) in PTRS: self.take(smodelCount*36)
        if g(dp+88) in PTRS:
            sb = self.take(surfaceCount*80)
            for i in range(surfaceCount): self.slot(sb+i*80+48, 'surf.material')
        if g(dp+92) in PTRS:
            sb = self.take(smodelCount*208)
            for i in range(smodelCount): self.slot(sb+i*208+32, 'smdi.model')
            for i in range(smodelCount):
                io = sb + i*208 + 80
                for k in range(4):
                    lo = io + k*32
                    if self.u32(lo) in PTRS: self.take(self.u16(lo+24)*4)

        for moff in range(1020, 1036, 4):
            if g(moff) in PTRS: self.material('tail%d' % moff)
            else: self.slot(self.body+moff, 'tail.material%d' % moff)
        noc = g(1036)
        if g(1040) in PTRS: self.take(noc*68)
        hlc, htc = g(1052), g(1056)
        if g(1060) in PTRS: self.take(hlc*56)
        if g(1064) in PTRS: self.take(htc*32)

        self.tail_file = self.f
        self.take(TAIL_SIZE)   # siege-skin shader tail (self-aliases are class B)
        return self


def load_maps():
    gen_by_off, gen_by_name, gen_by_index = {}, {}, {}
    for ln in open(GEN_TSV):
        p = ln.rstrip('\n').split('\t')
        t, n, o = int(p[0]), p[1], int(p[2], 16)
        if not n: continue
        gen_by_off[o] = (t, n)
        gen_by_name.setdefault((t, n), o)
        if len(p) >= 4:           # top-level line carries the list index
            gen_by_index[int(p[3])] = (t, n)
    our_by_name = {}
    for ln in open(OUR_TSV):
        t, n, blk, o = ln.rstrip('\n').split('\t')
        if int(blk) == 5:
            our_by_name[(int(t), n)] = int(o, 16)
    return gen_by_off, gen_by_name, gen_by_index, our_by_name


def list_base(zr):
    strb = sum(len(s)+1 for s in zr.strings[1:])
    return (zr.string_count*4 + strb + 3) & ~3


def build_our_list_names(zo):
    """Replicate CreateXAssetList's write-order filter over the write log so we
    can name every OUR list entry; assert the type sequence matches exactly."""
    omit = set()
    if os.environ.get('OAT_OMIT_LIST'):
        omit = {l.strip() for l in open(os.environ['OAT_OMIT_LIST']) if l.strip()}
    GUARD = {17, 11, 12, 16, 13, 15}
    rows = [tuple(ln.rstrip('\n').split('\t')[:2]) for ln in open(OUR_TSV)]
    pred = [(int(t), n) for t, n in rows
            if int(t) != 48 and not (n in omit and int(t) not in GUARD)]
    # The write-log replication is byte-exact up to the tail world-assets (a lone
    # off-by-one there from the inlined genuine MapEnts/AddonMapEnts pair). Build
    # the (type,name)->index map for the verified prefix only; every class-C
    # reference (XMODEL/TECHSET) lives well before that point.
    idx = {}
    good = 0
    for i in range(min(len(pred), zo.asset_count)):
        if pred[i][0] != zo.assets[i][1]:
            break
        idx.setdefault(pred[i], i)
        good = i + 1
    print('our-list replicated & type-verified for %d/%d entries' % (good, zo.asset_count))
    return idx


def make_name_ref(name):
    """A ',name'-style DB_Find reference: the loader treats a pointer whose bytes
    begin with ',' + name + NUL as a runtime asset lookup. Returned as raw bytes
    to splice at the slot (little quirk: it occupies the 4-byte slot only when the
    name fits; longer names need out-of-line storage which this blob can't add, so
    callers fall back to a default in-zone asset instead)."""
    return None  # not representable in a fixed 4-byte slot; see caller fallback


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'inventory'
    zd = open(GEN_ZONE, 'rb').read()
    blob = bytearray(open(BLOB_IN, 'rb').read())
    u32 = lambda o: struct.unpack_from('>I', zd, o)[0]
    gen_by_off, gen_by_name, gen_by_index, our_by_name = load_maps()

    zg = wiiu_zone.ZoneReader(zd); zg.read_string_table(); zg.read_asset_list()
    zo = wiiu_zone.ZoneReader(open(OUR_ZONE, 'rb').read())
    zo.read_string_table(); zo.read_asset_list()
    gen_list_lo, gen_list_hi = list_base(zg), list_base(zg) + zg.asset_count*8
    our_list_lo = list_base(zo)

    our_base = our_by_name[(17, 'maps/mp/mp_raid.d3dbsp')]
    DELTA = our_base - GEN_BASE

    # genuine images sorted by block-5 offset, for nearest-name resolution of the
    # inline-material texture refs (shared common_mp textures whose exact genuine
    # block offset the OAT loader never logs, since it alias-loads them).
    gen_imgs = sorted((o, n) for (t, n), o in gen_by_name.items() if t == 8)
    gen_img_offs = [o for o, _ in gen_imgs]
    import bisect
    def nearest_img_name(t):
        j = bisect.bisect_right(gen_img_offs, t) - 1
        return gen_imgs[j][1] if j >= 0 else None
    # a guaranteed-valid in-zone image body (last-resort texture fallback)
    fallback_img = next((o for (t, n), o in our_by_name.items() if t == 8), None)

    w = Walk(zd).run()
    file_ok = w.f == GEN_END_FILE
    print('genuine walk file end 0x%x (want 0x%x) %s' %
          (w.f, GEN_END_FILE, 'OK' if file_ok else 'BAD'))
    print('our GfxWorld base 0x%x  DELTA 0x%x  gen_index entries %d' %
          (our_base, DELTA, len(gen_by_index)))

    from collections import Counter, defaultdict
    cls = Counter(); miss = defaultdict(list)
    patched = Counter(); unresolved = []

    def blob_patch(fp, val):
        struct.pack_into('>I', blob, fp - (GEN_BODY_FILE + 8), val)

    # a default fallback asset per type present in OUR zone (for shared assets
    # our lean zone omits — keeps geometry rendering; texture may be wrong)
    def any_our(pcType):
        for (t, n), off in our_by_name.items():
            if t == pcType:
                return off
        return None

    for fp, kind in w.slots:
        v = u32(fp); t = dec(v)
        if GEN_BASE <= t < GEN_GWMP_BASE:
            cls['B'] += 1
            if mode == 'remap':
                blob_patch(fp, enc(t + DELTA)); patched['B'] += 1
        elif gen_list_lo <= t < gen_list_hi and (t - gen_list_lo) % 8 == 4:
            cls['C'] += 1
            i = (t - gen_list_lo) // 8
            info = gen_by_index.get(i)
            if info is None:
                unresolved.append((hex(fp), kind, 'gen list idx %d unnamed' % i)); continue
            key = info
            if key not in our_by_name:
                # same name absent in our zone -> fall back to any asset of type
                fb = any_our(info[0])
                if fb is None:
                    unresolved.append((hex(fp), kind, 'no our %s and no type fallback' % (info,))); continue
                if mode == 'remap': blob_patch(fp, enc(fb + 4 + 0)); patched['C_fb'] += 1
                miss['C_name'].append(info[1]); continue
            # class C target is OUR list ENTRY slot address (&assetList[i].header.data)
            oi = our_list_index.get(key)
            if oi is None:
                unresolved.append((hex(fp), kind, 'our list idx missing %s' % (info,))); continue
            if mode == 'remap':
                blob_patch(fp, enc(our_list_lo + oi*8 + 4)); patched['C'] += 1
        else:
            cls['A'] += 1
            # shared asset below GEN_BASE. Try exact struct base / name-string first.
            info = gen_by_off.get(t)
            if info is None:
                for typ, noff in NAME_OFF.items():
                    c = gen_by_off.get(t - noff)
                    if c and c[0] == typ: info = (typ, c[1]); break
            is_img = kind.split('@')[0] in ('mat.texdef.image', 'probe.image',
                                            'lightmap.image', 'outdoorImage')
            # GFXREMAP_FLAT_TEX=<imgname>: force EVERY external (class-A) texture
            # ref to one known-good 2D image. Bisection: isolates whether the
            # nearest-name texture guesses are what faults world render setup.
            flat = os.environ.get('GFXREMAP_FLAT_TEX')
            if info is None and is_img and flat and (8, flat) in our_by_name:
                info = (8, flat); miss['A_img_flat'].append(flat)
            if info is None and is_img:
                # inline-material texture ref: resolve by NEAREST genuine image
                # name (shared decal/detail textures our zone carries by name).
                nm = nearest_img_name(t)
                if nm is not None and (8, nm) in our_by_name:
                    info = (8, nm); miss['A_img_nearest'].append(nm)
            if info is None and kind == 'body.skyBoxModel':
                if mode == 'remap': blob_patch(fp, 0)   # no skybox model
                patched['A_null'] += 1; continue
            if info is None and is_img:
                if fallback_img is None:
                    unresolved.append((hex(fp), kind, 'ext img 0x%x, no fallback' % t)); continue
                if mode == 'remap': blob_patch(fp, enc(fallback_img)); patched['A_imgfb'] += 1
                miss['A_img_fb'].append(hex(t)); continue
            if info is None:
                unresolved.append((hex(fp), kind, 'external 0x%x unknown' % t)); continue
            miss['A_ref'].append(info[1])
            if mode == 'remap':
                if info in our_by_name:
                    tgt = our_by_name[info]
                    blob_patch(fp, enc(tgt))    # alias -> asset body (block-5)
                    patched['A'] += 1
                else:
                    fb = any_our(info[0])
                    if fb is None:
                        unresolved.append((hex(fp), kind, 'no our %s / fallback' % (info,))); continue
                    blob_patch(fp, enc(fb)); patched['A_fb'] += 1

    print('alias classes:', dict(cls), ' total', sum(cls.values()))
    if miss.get('C_name'):
        print('  class-C names missing in our zone:', len(miss['C_name']),
              set(miss['C_name']) - set() and list(sorted(set(miss['C_name'])))[:6])
    if miss.get('A_ref'):
        print('  class-A shared refs:', Counter(miss['A_ref']).most_common(8))

    # AUTHORITATIVE supplementary pass (class B): the structural walk can miss
    # ALIAS fields (they consume no stream bytes, so the end-check can't catch a
    # miss). OAT_PTR_LOG (ptr_resolve.tsv) records every internal pointer the
    # genuine loader actually resolves. Any blob word still holding an
    # authoritative in-span target after the structural pass is a MISSED internal
    # pointer (e.g. the portal->cell backref at portal+52) — apply +DELTA. Only
    # exact-value matches to the specific authoritative target set are touched, so
    # vertex/pixel data false-positives are not (astronomically unlikely to equal
    # a specific enc(target)).
    auth_in_span = set()
    try:
        for l in open('ptr_resolve.tsv'):
            blk, off, kind = l.rstrip('\n').split('\t')
            if blk == '5':
                o = int(off, 16)
                if GEN_BASE <= o < GEN_GWMP_BASE:
                    auth_in_span.add(o)
    except FileNotFoundError:
        print('  WARNING: ptr_resolve.tsv missing — skipping authoritative pass')
    auth_vals = {enc(o): o for o in auth_in_span}
    supp = 0
    if mode == 'remap' and auth_vals:
        for i in range(0, len(blob) - 3, 4):
            v = struct.unpack_from('>I', blob, i)[0]
            if v in auth_vals:
                struct.pack_into('>I', blob, i, enc(auth_vals[v] + DELTA))
                supp += 1
    print('authoritative in-span targets: %d ; supplementary +DELTA patches (missed by walk): %d'
          % (len(auth_in_span), supp))

    if mode == 'inventory':
        return

    if not file_ok:
        raise SystemExit('genuine walk not exact — aborting')
    patched['B_supp'] = supp
    print('patched:', dict(patched), ' unresolved:', len(unresolved))
    for u in unresolved[:20]: print('  UNRESOLVED', u)
    if unresolved:
        raise SystemExit('unresolved aliases remain — not writing output')
    open(BLOB_OUT, 'wb').write(bytes(blob))
    print('wrote %s (%d bytes)' % (BLOB_OUT, len(blob)))


# our_list_index is built in main() but referenced in the loop; bind lazily
our_list_index = {}

if __name__ == '__main__':
    # populate our_list_index before main's loop uses it
    _zo = wiiu_zone.ZoneReader(open(OUR_ZONE, 'rb').read())
    _zo.read_string_table(); _zo.read_asset_list()
    our_list_index = build_our_list_names(_zo)
    main()
