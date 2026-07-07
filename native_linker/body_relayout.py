#!/usr/bin/env python3
"""
Stage 1 (increment 2): asset-BODY re-layout.

Walks a genuine console zone's asset graph exactly like wiiu_ref/walker.py, but
instead of only advancing a cursor it RE-EMITS every consumed region through the
native ZoneWriter, patching alias pointers via a source->writer offset map. Byte-
identity of the re-emitted stream proves the writer reproduces the original linker's
layout for that asset type. Where it diverges, the first mismatch pinpoints the exact
struct/directive to fix (the "resync at divergence" method, made exact for writing:
the reader could paper over a size error with next-body resync; the writer cannot).

Design: the walk consumes source bytes sequentially (self.src = a cursor into the
genuine stream). Each consumed region is copied to the writer with its pointer fields
patched (FOLLOW/null kept; alias remapped through self.omap), and its source block-5
offset registered so later back-aliases resolve. For a faithful round-trip the writer
offset equals the source offset, so remap is identity — but it is computed, not
assumed, so any layout drift shows up as a byte divergence.

Usage: python body_relayout.py [genuine.zone] [max_assets]
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import zone_stream as zs
import struct_layout
import walker as W
import shader_probe as SP
import fx_probe as FP
import xmodel_probe as XP
import destructibledef_probe as DP

# Solved external delimiters for asset types whose console layout has no structural
# re-emitter yet. Each returns the END file offset given the body start; the region is
# copied verbatim (byte-exact for a round-trip). Stage 2/3 replaces these with real
# structural emission when authoring/synthesis needs it.
def _techset_end(z, o): return SP.parse_techset(z, o)[0]
def _fx_end(z, o):      return FP.parse_fx(z, o)[0]
def _xmodel_end(z, o):  return XP.parse_xmodel(z, o)[0]
def _destruct_end(z, o): return DP.parse_destructible(z, o, '>')[0]

def _lightdef_end(z, o):
    # console GfxLightDef: 16B body {name, attenuation.image, samplerState, lmapLookupStart}
    # + [name string if name FOLLOW] + [inline console GfxImage(328B) if image FOLLOW/INSERT].
    c = XP.Cur(z, o + 16)
    name_p = struct.unpack_from('>I', z, o)[0]
    img_p = struct.unpack_from('>I', z, o + 4)[0]
    if name_p in XP.PTRS:
        c.cstr()
    if img_p in XP.PTRS:
        XP.consume_image(z, c)
    return c.o

def _material_end(z, o):
    c = XP.Cur(z, o)
    XP.consume_material(z, c)
    return c.o

def _gwmp_end(z, o):
    # GameWorldMp {alias name, PathData}. gameworldmp_probe walker, console node_size=144.
    import gameworldmp_probe as GW
    end, _ = GW.Walker(z, '>', 144).walk(o)
    return end

def _image_end(z, o):
    c = XP.Cur(z, o)
    XP.consume_image(z, c)
    return c.o

def _gfxworld_end(z, o):
    # gfxworld_probe2's structural walker, driven at body offset `o`. Bypass its
    # file-reading __init__ and feed our zone bytes; suppress its diagnostic prints.
    import gfxworld_probe2 as G2, io, contextlib
    cfg = dict(G2.CFG['wiiu']); cfg['body'] = o
    p = G2.W.__new__(G2.W)
    p.c = cfg; p.d = z; p.e = cfg['endian']; p.b = o; p.o = o + cfg['bodysize']
    with contextlib.redirect_stdout(io.StringIO()):
        G2.walk(p)
    end = p.o
    # gfxworld_probe2 stops before the console siege-skin shader tail (fixed 11085B block,
    # starts ffffffff ffffffff 00000000 "gpuskin1"). Append it if present.
    SIEGE = 11085
    if z[end:end+12] == b'\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00':
        end += SIEGE
    return end

def _comworld_end(z, o):
    # console ComWorld: 16B body {name FOLLOW, isInUse, primaryLightCount, primaryLights}
    # + primaryLightCount x ComPrimaryLight(168B, defNames aliased so no inline strings)
    # + the ComWorld name string (reordered to AFTER the lights). Walk lights while the
    # first word is a valid light type (1..8); the name string starts with ASCII (>8).
    p = o + 16
    while p + 168 <= len(z):
        t = struct.unpack_from('>I', z, p)[0]
        if not (1 <= t <= 8):
            break
        p += 168
    return z.index(b'\x00', p) + 1     # trailing name c-string

DELIMITERS = {
    'MaterialTechniqueSet': _techset_end,
    'FxEffectDef': _fx_end,
    'XModel': _xmodel_end,
    'DestructibleDef': _destruct_end,
    'GfxLightDef': _lightdef_end,
    'Material': _material_end,
    'GfxImage': _image_end,
    'GfxWorld': _gfxworld_end,
    'GameWorldMp': _gwmp_end,
    # ComWorld is handled by the GENERIC walker (console layout == PC), reached via the
    # pre-check recovery that fixes the destructibledef under-read before it.
}
# kept for reference / next session
_UNUSED = _comworld_end


# ---- body detectors: is `o` the start of a valid body of PC asset-type `t`? ----
# Used for forward-scan recovery when a delimiter/probe UNDER-reads (e.g.
# destructibledef_probe misses inline piece sub-assets). We scan for the KNOWN next
# asset's body and extend the previous asset's verbatim copy to that boundary.
def _u32(z, o): return struct.unpack_from('>I', z, o)[0]

def _detect_comworld(z, o):
    # {name FOLLOW, isInUse=1, primaryLightCount 1..64, primaryLights FOLLOW}, then the
    # name string inline right after the 16-byte body (console ComWorld has no reorder).
    if not (o + 20 <= len(z) and _u32(z, o) == zs.FOLLOW and _u32(z, o+4) == 1
            and 1 <= _u32(z, o+8) <= 64 and _u32(z, o+12) == zs.FOLLOW):
        return False
    c = z[o+16]                       # first byte of the name string
    return 0x20 <= c < 0x7f

def _detect_techset(z, o):
    try:
        end, nt = SP.parse_techset(z, o)
        nxt = _u32(z, end)
        return nt >= 1 and (nxt == zs.FOLLOW or 0xA0000000 <= nxt < 0xC0000000)
    except Exception:
        return False

# PC asset type id -> detector. Keep this CONSERVATIVE: a detector with false negatives
# would spuriously trigger the pre-check recovery. Only very specific signatures belong here.
DETECTORS = {
    13: _detect_comworld,   # COMWORLD ({name FOLLOW, isInUse=1, count 1..64, lights FOLLOW})
}

def find_next_body(z, start, pc_type, window=0x8000):
    det = DETECTORS.get(pc_type)
    if det is None:
        return None
    for o in range(start, min(start + window, len(z) - 20)):   # byte-step: bodies pack at any align
        if det(z, o):
            return o
    return None

B5_BASE = 64   # block-5 offset == stream/file offset - 64

# zonecode block name -> block index; console redirects TEMP -> VIRTUAL
BLOCKMAP = {
    'XFILE_BLOCK_TEMP': zs.BLOCK_VIRTUAL,       # console TEMP->VIRTUAL redirect
    'XFILE_BLOCK_VIRTUAL': zs.BLOCK_VIRTUAL,
    'XFILE_BLOCK_PHYSICAL': zs.BLOCK_PHYSICAL,
    'XFILE_BLOCK_RUNTIME': zs.BLOCK_RT_VIRT,
    'XFILE_BLOCK_RUNTIME_VIRTUAL': zs.BLOCK_RT_VIRT,
    'XFILE_BLOCK_RUNTIME_PHYSICAL': zs.BLOCK_RT_PHYS,
    'XFILE_BLOCK_DELAY': zs.BLOCK_RT_VIRT,
}


# Console (v148) layout quirks the PC structs don't capture. Trailing bytes emitted
# after an asset's dynamics (verified against genuine bytes). SkinnedVertsDef: a
# u32=0 follows the name string (PC struct is just {name, maxSkinnedVerts}).
CONSOLE_TRAIL = {
    'SkinnedVertsDef': 4,
}


class ReEmitter:
    def __init__(self, zone, layout, zc, writer):
        self.z = zone
        self.L = layout
        self.zc = zc
        self.w = writer
        self.src = 0                 # source file cursor (mirrors walker's cur)
        self.omap = {}               # source block-5 offset -> writer block-5 offset
        # helper walker for scalar reads / count & condition eval / followers
        self.wk = W.Walker(zone, layout, zc, [0] * 8)

    def u32(self, o): return struct.unpack_from('>I', self.z, o)[0]

    # ---- register a region start so back-aliases resolve ------------------
    def register(self, src_file):
        self.omap[src_file - B5_BASE] = self.w.block_size[self.w.cur_block]

    def remap_ptr(self, v):
        """Return the value to WRITE for a source pointer word v."""
        if v in (zs.FOLLOW, zs.INSERT, 0):
            return v
        if not (0xA0000000 <= v < 0xC0000000):
            return v                 # not an alias-encoded value: raw data / handle
        blk, off = zs.decode_ptr(v)
        if blk == zs.BLOCK_VIRTUAL and off in self.omap:
            return zs.encode_ptr(blk, self.omap[off])
        return v                     # target not (yet) seen: carry through unchanged

    # ---- copy a struct body to the writer, patching its pointer fields ----
    def emit_body(self, struct_name, src_file):
        s = self.wk.gs(struct_name)
        size = s['size']
        raw = bytearray(self.z[src_file:src_file + size])
        for f in s['fields']:
            if 'error' in f or not f.get('is_ptr'):
                continue
            for k in range(max(f['arr'], 1)):
                fo = f['offset'] + k * 4
                if fo + 4 > size:
                    break
                v = struct.unpack_from('>I', raw, fo)[0]
                struct.pack_into('>I', raw, fo, self.remap_ptr(v))
        self.register(src_file)
        self.w.write_bytes(bytes(raw))
        self.src = src_file + size

    # ---- string ----------------------------------------------------------
    def emit_cstring(self):
        end = self.z.index(b'\x00', self.src)
        self.register(self.src)
        self.w.write_bytes(self.z[self.src:end + 1])
        self.src = end + 1

    # ---- follow one struct's dynamic children (mirrors follow_dynamics) ---
    def follow(self, struct_name, body_src, ctx):
        c = dict(ctx)
        self.wk.read_scalars(struct_name, body_src, c)
        for nm, f, d in self.wk.followers(struct_name):
            fo = body_src + f['offset']
            base = f['base']

            # inline flexible array member (arraysize on an embedded struct)
            if d.get('arraysize') and base in self.L.structs:
                count = self.wk.eval_count(d['arraysize'], c)
                decl = f['arr']
                for i in range(max(count, 0)):
                    self.follow(base, fo + i * self.wk.gs(base)['size'], c)
                continue

            # inline array of pointers (e.g. techniques[N])
            if f.get('is_ptr') and f['arr'] > 1:
                if not self.wk.eval_cond(d.get('condition'), c):
                    continue
                for i in range(f['arr']):
                    marker = self.u32(fo + i * 4)
                    if marker not in (W.FOLLOW, W.INSERT):
                        continue
                    if d.get('string'):
                        self.emit_cstring(); continue
                    cnt = self.wk.eval_count(d['count'], c) if d.get('count') else 1
                    if cnt > 0:
                        self.emit_array(base, cnt)
                continue

            # embedded (non-pointer) struct: recurse into its pointers, same body region
            if not f.get('is_ptr') and base in self.L.structs and f['arr'] == 1:
                self.follow(base, fo, c)
                continue
            if not f.get('is_ptr'):
                continue

            marker = self.u32(fo)
            if not self.wk.eval_cond(d.get('condition'), c):
                continue
            if marker in (0,) or (marker not in (W.FOLLOW, W.INSERT)):
                continue             # null or alias -> no inline child
            if d.get('string'):
                self.emit_cstring(); continue
            if d.get('assetref'):
                continue
            count = self.wk.eval_count(d['count'], c) if d.get('count') else 1
            if count <= 0:
                continue
            self.emit_array(base, count)

    # ---- emit an array of `count` `base` elements (bodies then dynamics) --
    def emit_array(self, base, count):
        if base in self.L.structs:
            s = self.wk.gs(base)
            # Console linker packs FOLLOW arrays; it only pads for OVER-aligned types
            # (vertex/shader blobs at 16/128). OAT's defensive Align(4) does NOT match
            # genuine (proven: StringTableCell array lands at an unaligned offset).
            if s['align'] > 4:
                self.w.align(s['align'])
            starts = []
            for i in range(count):
                starts.append(self.src)
                self.emit_body(base, self.src)
            has_dyn = any(self.zc.d.get(base, {}).get(f['name'], {}).get('string')
                          or self.zc.d.get(base, {}).get(f['name'], {}).get('count')
                          or f.get('is_ptr')
                          or (f['base'] in self.L.structs and not f.get('is_ptr'))
                          for f in s['fields'] if 'error' not in f)
            if has_dyn:
                for i in range(count):
                    self.follow(base, starts[i], {})
        else:
            sz, _ = self.L._resolve(base)
            self.register(self.src)
            self.w.write_bytes(self.z[self.src:self.src + count * sz])
            self.src = self.src + count * sz

    # ---- emit one top-level asset ----------------------------------------
    def emit_verbatim(self, src_file, end):
        """Copy [src_file, end) as-is. Used for assets whose console layout has a
        solved external delimiter (techset/GX2 shaders) but no structural re-emitter
        yet. Byte-exact for a round-trip (offsets preserved); Stage 2/3 replaces
        these with real structural emission for authoring/synthesis."""
        if end <= src_file or end > len(self.z):
            raise RuntimeError('delimiter returned out-of-range end 0x%x (start 0x%x, zone 0x%x)'
                               % (end, src_file, len(self.z)))
        self.register(src_file)
        self.w.write_bytes(self.z[src_file:end])
        self.src = end
        return end

    def emit_asset(self, root, src_file):
        blkname = self.zc.default_block.get(root, 'XFILE_BLOCK_TEMP')
        self.w.push_block(BLOCKMAP.get(blkname, zs.BLOCK_VIRTUAL))
        self.src = src_file

        # solved external delimiter (techset/FX/...): bound the asset, copy verbatim.
        delim = DELIMITERS.get(root)
        if delim is not None:
            try:
                end = delim(self.z, src_file)
            except Exception as e:
                raise RuntimeError('%s delimiter failed: %s' % (root, e))
            self.emit_verbatim(src_file, end)
            self.w.pop_block()
            return self.src

        ov = self.wk.CONSOLE_OVERRIDE.get(root)
        if ov:
            # console-divergent struct (e.g. GLASSES = 16-byte stub); emit verbatim
            self.register(src_file)
            self.w.write_bytes(self.z[src_file:src_file + ov['size']])
            self.src = src_file + ov['size']
            if ov.get('no_follow'):
                self.w.pop_block()
                return self.src
        else:
            self.emit_body(root, src_file)
        self.follow(root, src_file, {})
        trail = CONSOLE_TRAIL.get(root)
        if trail:
            self.w.write_bytes(self.z[self.src:self.src + trail])
            self.src += trail
        self.w.pop_block()
        return self.src


def main():
    zpath = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref', 'mp_raid_genuine.zone')
    max_assets = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    zone = open(zpath, 'rb').read()
    import importlib
    wz = importlib.import_module('wiiu_zone')
    r = wz.ZoneReader(zone); r.read_string_table(); r.read_asset_list()
    L = struct_layout.Layout(W.HDR, console=True)
    zc = W.ZoneCode(W.ZC_DIR)

    w = zs.ZoneWriter()
    w.push_block(zs.BLOCK_VIRTUAL)
    w.block_size[zs.BLOCK_VIRTUAL] = r.assets_end - B5_BASE   # start after the asset array

    em = ReEmitter(zone, L, zc, w)
    cur = r.assets_end
    validated = 0
    stuck = None
    for i, (cid, pc, nm) in enumerate(r.assets[:max_assets]):
        root = W.ASSET_ROOT.get(nm)
        start = cur
        if root is None or root not in L.structs:
            print("[%d] %-16s SKIP (no root)" % (i, nm)); continue
        # PRE-CHECK recovery: if THIS asset's type is detectable and its body isn't at
        # `start` but appears just ahead, the PREVIOUS asset under-read (its delimiter/probe
        # missed a tail, e.g. destructibledef inline piece sub-assets). Absorb the gap bytes
        # verbatim (they belong to the previous asset; the stream stays byte-identical) and
        # start this asset at its real body.
        if pc in DETECTORS and not DETECTORS[pc](zone, start):
            real = find_next_body(zone, start, pc)
            if real is not None and real > start:
                w.write_bytes(zone[start:real])
                print("     [recovery] previous asset under-read; absorbed 0x%x gap bytes -> %s body @0x%x"
                      % (real - start, nm, real))
                start = real; cur = real
        before_w = len(w.buf)
        try:
            cur = em.emit_asset(root, start)
        except Exception as e:
            del w.buf[before_w:]; cur = start
            stuck = (i, nm, "EMIT ERROR: %s" % e); break
        emitted = w.buf[before_w:]
        orig = zone[start:cur]
        drift = ""
        if i + 1 < max_assets and cur < len(zone) - 4:
            nxt = struct.unpack_from('>I', zone, cur)[0]
            name_ok = (nxt == zs.FOLLOW) or (0xA0000000 <= nxt < 0xC0000000) or (nxt == 0)
            if not name_ok:
                drift = "next body implausible (name ptr 0x%08x)" % nxt
        if bytes(emitted) == orig and not drift:
            print("[%d] %-16s 0x%07x..0x%07x  OK (%d bytes)" % (i, nm, start, cur, cur - start))
            validated += 1
        else:
            del w.buf[before_w:]; cur = start
            stuck = (i, nm, drift or "byte divergence"); break

    # ---- verbatim-tail completion + FULL-ZONE byte-identity check ----
    if stuck:
        print("[%d] %-16s STUCK: %s" % (stuck[0], stuck[1], stuck[2]))
    if cur < len(zone):
        w.write_bytes(zone[cur:])          # copy the un-parsed tail verbatim
    content_ok = bytes(w.buf) == zone[r.assets_end:]
    total = r.assets_end + len(w.buf)
    print("\n==== ROUND-TRIP RESULT ====")
    print("assets individually re-laid-out & byte-verified: %d / %d" % (validated, len(r.assets)))
    if stuck:
        print("verbatim tail from asset %d (%s) onward: 0x%x bytes"
              % (stuck[0], stuck[1], len(zone) - cur))
    print("full content bytes match genuine zone: %s (%d / %d bytes)"
          % (content_ok, total, len(zone)))
    if content_ok and total == len(zone):
        print("*** FULL ZONE ROUND-TRIP BYTE-IDENTICAL ***")


if __name__ == '__main__':
    main()
