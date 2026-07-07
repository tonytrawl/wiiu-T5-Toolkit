#!/usr/bin/env python3
"""
Native Wii U (T6, v148) zone WALKER. Combines:
  - struct_layout.Layout  (32-bit field offsets/sizes from T6_Assets.h)
  - OAT ZoneCode .txt directives (set string/count/condition/reusable/block, reorder)
  - the big-endian decompressed zone stream

Walks the single linear DFS stream: for each asset, read its root struct body, then
follow FOLLOW pointers in (reordered) member order, advancing one cursor. Goal: walk
all 889 mp_raid assets and land exactly at zone end = full structural unlink.
"""
import os, re, struct, sys
import struct_layout

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
ZC_DIR = "../tools/ref_oat/src/ZoneCode/Game/T6/XAssets"
HDR = "../tools/ref_oat/src/Common/Game/T6/T6_Assets.h"

# asset-type name (from wiiu_zone PC enum) -> ZoneCode file / root struct
ASSET_ROOT = {
    "PHYSPRESET": "PhysPreset", "PHYSCONSTRAINTS": "PhysConstraints",
    "DESTRUCTIBLEDEF": "DestructibleDef", "XANIMPARTS": "XAnimParts", "XMODEL": "XModel",
    "MATERIAL": "Material", "TECHNIQUE_SET": "MaterialTechniqueSet", "IMAGE": "GfxImage",
    "CLIPMAP": "clipMap_t", "CLIPMAP_PVS": "clipMap_t", "COMWORLD": "ComWorld",
    "GAMEWORLD_MP": "GameWorldMp", "GAMEWORLD_SP": "GameWorldSp", "MAP_ENTS": "MapEnts",
    "GFXWORLD": "GfxWorld", "LIGHT_DEF": "GfxLightDef", "FONT": "Font_s",
    "FONTICON": "FontIcon", "LOCALIZE_ENTRY": "LocalizeEntry", "RAWFILE": "RawFile",
    "STRINGTABLE": "StringTable", "LEADERBOARD": "LeaderboardDef", "DDL": "ddlRoot_t",
    "GLASSES": "Glasses", "EMBLEMSET": "EmblemSet", "SCRIPTPARSETREE": "ScriptParseTree",
    "KEYVALUEPAIRS": "KeyValuePairs", "MEMORYBLOCK": "MemoryBlock",
    "ADDON_MAP_ENTS": "AddonMapEnts", "TRACER": "TracerDef", "SKINNEDVERTS": "SkinnedVertsDef",
    "QDB": "Qdb", "SLUG": "Slug", "FOOTSTEP_TABLE": "FootstepTableDef",
    "FOOTSTEPFX_TABLE": "FootstepFXTableDef", "ZBARRIER": "ZBarrierDef",
    "FX": "FxEffectDef", "IMPACT_FX": "FxImpactTable", "SOUND": "SndBank",
    "SOUND_PATCH": "SndPatch", "MENU": "menuDef_t", "MENULIST": "MenuList",
    "VEHICLEDEF": "VehicleDef", "WEAPONDEF": "WeaponVariantDef",
    "SNDDRIVER_GLOBALS": "SndDriverGlobals", "XGLOBALS": "XGlobals",
}


class ZoneCode:
    """Parse all T6 ZoneCode .txt into per-struct member directives."""
    def __init__(self, zc_dir):
        self.d = {}          # struct -> member -> {string,scriptstring,count,condition,reusable,arraysize,assetref}
        self.default_block = {}   # struct -> block
        self.reorder = {}    # struct -> [members]
        for fn in os.listdir(zc_dir):
            if fn.endswith('.txt'):
                self._parse(os.path.join(zc_dir, fn))

    def _md(self, st, mem):
        return self.d.setdefault(st, {}).setdefault(mem, {})

    def _parse(self, path):
        cur = None
        lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
        i = 0
        while i < len(lines):
            ln = lines[i].split('//')[0].strip()
            i += 1
            if not ln:
                continue
            if ln.startswith('use '):
                cur = ln[4:].strip().rstrip(';')
                continue
            if ln.startswith('reorder'):
                # reorder: a b c ...;  (may span lines until ';')
                buf = ln
                while ';' not in buf and i < len(lines):
                    buf += ' ' + lines[i].split('//')[0].strip(); i += 1
                body = buf.split(':', 1)[1].rstrip(';') if ':' in buf else buf[len('reorder'):].rstrip(';')
                self.reorder[cur] = body.split()
                continue
            if not ln.startswith('set '):
                continue
            # gather until ';'
            while ';' not in ln and i < len(lines):
                ln += ' ' + lines[i].split('//')[0].strip(); i += 1
            ln = ln.rstrip(';').strip()
            parts = ln.split(None, 2)   # set <verb> <rest>
            verb = parts[1]
            rest = parts[2] if len(parts) > 2 else ''
            if verb == 'block':
                # "set block XFILE_BLOCK_X" (struct default) or "set block member BLOCK"
                toks = rest.split()
                if len(toks) == 1:
                    self.default_block[cur] = toks[0]
                else:
                    st, mem = self._sm(toks[0], cur)
                    self._md(st, mem)['block'] = toks[1]
                continue
            # verbs with a member as first token
            toks = rest.split(None, 1)
            member = toks[0]
            arg = toks[1] if len(toks) > 1 else ''
            st, mem = self._sm(member, cur)
            md = self._md(st, mem)
            if verb == 'string': md['string'] = True
            elif verb == 'scriptstring': md['scriptstring'] = True
            elif verb == 'reusable': md['reusable'] = True
            elif verb == 'count': md['count'] = arg.strip()
            elif verb in ('arraysize', 'arraycount'): md['arraysize'] = arg.strip()
            elif verb == 'condition': md['condition'] = arg.strip()
            elif verb == 'assetref': md['assetref'] = True
            elif verb == 'allocalign': md['allocalign'] = arg.strip()
            elif verb == 'action': md['action'] = arg.strip()
            elif verb == 'name': md['name'] = arg.strip()

    def _sm(self, token, cur):
        if '::' in token:
            st, mem = token.split('::', 1)
            return st, mem
        return cur, token


class Walker:
    def __init__(self, zone, layout, zc, block_sizes=None):
        self.z = zone; self.L = layout; self.zc = zc
        self.n = len(zone)
        self.block_sizes = block_sizes or [0]*8
        self.errors = []

    def u16(self, o): return struct.unpack('>H', self.z[o:o+2])[0]
    def u32(self, o): return struct.unpack('>I', self.z[o:o+4])[0]

    def eval_count(self, expr, ctx):
        e = expr.strip()
        # array indexing name[k] -> ctx['name'][k]
        def repl(m):
            nm, idx = m.group(1), m.group(2)
            v = ctx.get(nm)
            return str(v[int(idx)] if isinstance(v, list) else 0)
        e = re.sub(r'([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]', repl, e)
        e = re.sub(r'\b([A-Za-z_]\w*)\b', lambda m: str(ctx.get(m.group(1), 0))
                   if not m.group(1).isdigit() else m.group(1), e)
        try:
            return int(eval(e, {"__builtins__": {}}, {}))
        except Exception:
            return 0

    def eval_cond(self, expr, ctx):
        """Evaluate a ZoneCode condition (e.g. 'type == MTL_ARG_LITERAL_VERTEX_CONST || ...').
        Returns True if the pointed data is present. Unknown -> True (conservative)."""
        if not expr:
            return True
        e = expr.strip()
        if e == 'never':
            return False
        e = e.replace('||', ' or ').replace('&&', ' and ')

        def sub(m):
            w = m.group(0)
            if w in ('or', 'and', 'not'):
                return w
            if w in ctx:
                v = ctx[w]
                return str(v[0] if isinstance(v, list) else v)
            if w in self.L.enum_vals:
                return str(self.L.enum_vals[w])
            return '0'
        e = re.sub(r'[A-Za-z_]\w*', sub, e)
        try:
            return bool(eval(e, {"__builtins__": {}}, {}))
        except Exception:
            return True

    def read_scalars(self, struct_name, off, ctx):
        """Read scalar (non-pointer) field values from a struct body into ctx (flat)."""
        s = self.gs(struct_name)
        for f in s['fields']:
            if 'error' in f or f.get('is_ptr'):
                continue
            base = f['base']
            fo = off + f['offset']
            if base in self.L.structs:
                # embedded struct: recurse for its scalars (flat, shared names ok in-scope)
                self.read_scalars(base, fo, ctx)
                continue
            sz = f['size'] // max(f['arr'], 1)
            if f['arr'] > 1:
                vals = []
                for k in range(f['arr']):
                    vals.append(self._scalar(base, fo + k*sz))
                ctx[f['name']] = vals
            else:
                ctx[f['name']] = self._scalar(base, fo)

    def _scalar(self, base, o):
        s, _ = self.L._resolve(base)
        if s == 1: return self.z[o]
        if s == 2: return self.u16(o)
        return self.u32(o)

    def followers(self, struct_name):
        """Ordered list of (member, field, directives) to follow. reorder if present, else field order.
        Includes embedded-struct members (recursed)."""
        s = self.gs(struct_name)
        fields = {f['name']: f for f in s['fields'] if 'error' not in f}
        order = self.zc.reorder.get(struct_name) or [f['name'] for f in s['fields'] if 'error' not in f]
        out = []
        for nm in order:
            f = fields.get(nm)
            if not f:
                continue
            d = self.zc.d.get(struct_name, {}).get(nm, {})
            out.append((nm, f, d))
        return out

    def skip_cstring(self, cur):
        end = self.z.index(b'\x00', cur)
        return end + 1

    # file-backed blocks (asset structs/strings live here): TEMP, VIRTUAL, PHYSICAL
    FILE_BLOCKS = (0, 5, 6)

    def is_ptr_marker(self, v, name_like=False):
        """True if v is a valid zone pointer. name_like tightens it: a name pointer
        is FOLLOW or an alias into a FILE-BACKED block within its declared size
        (never a runtime/streamer block, never ASCII text)."""
        if v == FOLLOW or v == INSERT:
            return True
        if v == 0:
            return not name_like  # a name is never null
        blk = (v - 1) >> 29
        off = (v - 1) & 0x1FFFFFFF
        if blk >= 8:
            return False
        bs = self.block_sizes[blk] if blk < len(self.block_sizes) else 0
        if name_like:
            return blk in self.FILE_BLOCKS and off < bs + 0x1000
        # general pointer: file blocks in-range; runtime/streamer may hold big refs
        if blk in self.FILE_BLOCKS:
            return off < bs + 0x1000
        return off < 0x2000000  # runtime/streamer: bounded slack

    def is_plausible_body(self, struct_name, off):
        """Type-aware check: could `off` be the start of a `struct_name` body?
        Field 0 (name) must be a real name pointer; every pointer field a valid marker."""
        if struct_name not in self.L.structs:
            return False
        s = self.gs(struct_name)
        if off + s['size'] > self.n or not s['fields']:
            return False
        f0 = s['fields'][0]
        if not f0.get('is_ptr'):
            return False  # all T6 asset roots start with a name pointer
        if not self.is_ptr_marker(self.u32(off), name_like=True):
            return False
        ptrs = 1
        for f in s['fields'][1:]:
            if 'error' in f or not f.get('is_ptr') or f['arr'] != 1:
                continue
            if not self.is_ptr_marker(self.u32(off + f['offset'])):
                return False
            ptrs += 1
        # verify the name actually resolves to a printable string
        v0 = self.u32(off)
        if v0 == FOLLOW:
            # name string is the first inline datum for most roots; peek after body
            pass
        return ptrs >= 1

    # console (v148) struct layouts that diverge from OAT's PC definitions,
    # derived from the genuine zone. size = bytes consumed; no_follow = no dynamic data.
    CONSOLE_OVERRIDE = {
        'Glasses': {'size': 16, 'no_follow': True},
    }

    # console field-array-size patches: struct -> {field: console_arr}. Derived from
    # genuine bytes. e.g. MaterialTechniqueSet.techniques is [32] on console, [36] on PC.
    CONSOLE_FIELD_ARR = {
        'MaterialTechniqueSet': {'techniques': 32},
    }

    _patched = {}

    def gs(self, name):
        """Layout for `name` with console field-array patches applied (cached)."""
        # console field-array patches (e.g. MaterialTechniqueSet.techniques 36->32) apply
        # ONLY to console layouts; a PC-mode walk (self.L.console False) keeps the PC arrays.
        patch = self.CONSOLE_FIELD_ARR.get(name) if getattr(self.L, 'console', False) else None
        if not patch:
            return self.L.get(name)
        if name in self._patched:
            return self._patched[name]
        import copy
        s = copy.deepcopy(self.L.get(name))
        for f in s['fields']:
            if f.get('name') in patch and 'error' not in f:
                old_arr = f['arr']
                new_arr = patch[f['name']]
                elem = f['size'] // max(old_arr, 1)
                s['size'] -= (old_arr - new_arr) * elem
                f['arr'] = new_arr
                f['size'] = new_arr * elem
        self._patched[name] = s
        return s

    def walk(self, struct_name, cur, depth=0):
        """One struct: advance past its body, then follow its dynamic children."""
        ov = self.CONSOLE_OVERRIDE.get(struct_name)
        if ov:
            cur += ov['size']
            if ov.get('no_follow'):
                return cur
        s = self.gs(struct_name)
        body = cur
        cur += s['size']
        return self.follow_dynamics(struct_name, body, cur, {}, depth)

    def follow_dynamics(self, struct_name, body, cur, parent_ctx, depth):
        """Follow FOLLOW pointer members of the struct whose body is at `body`.
        `cur` points at the next free stream position (after all sibling bodies)."""
        ctx = dict(parent_ctx)
        self.read_scalars(struct_name, body, ctx)
        for nm, f, d in self.followers(struct_name):
            fo = body + f['offset']
            base = f['base']
            # elemsz is unused below; guard the resolve so PC-mode pointer fields to
            # unresolvable GPU-handle types (ID3D11*) don't raise (console omits them).
            elemsz = self.L._resolve(base)[0] if base in self.L.structs else 4

            # inline flexible array member (e.g. passArray[1] with arraysize passCount):
            # the body holds `count` elements inline (s['size'] only counted the declared [1..N]).
            if d.get('arraysize') and base in self.L.structs:
                count = self.eval_count(d['arraysize'], ctx)
                decl = f['arr']  # declared array length already inside s['size']
                if count > decl:
                    cur += (count - decl) * self.gs(base)['size']
                for i in range(max(count, 0)):
                    cur = self.follow_dynamics(base, fo + i*self.gs(base)['size'], cur, ctx, depth)
                continue

            # inline array of pointers in the body (e.g. techniques[36]): follow each slot
            if f.get('is_ptr') and f['arr'] > 1:
                if not self.eval_cond(d.get('condition'), ctx):
                    continue
                for i in range(f['arr']):
                    marker = self.u32(fo + i*4)
                    if marker != FOLLOW and marker != INSERT:
                        continue
                    if d.get('string'):
                        cur = self.skip_cstring(cur); continue
                    cnt = self.eval_count(d['count'], ctx) if d.get('count') else 1
                    if cnt > 0:
                        cur = self._read_array(base, cnt, cur, depth)
                continue

            # embedded struct (non-pointer): follow its inner pointers, same body region
            if not f.get('is_ptr') and base in self.L.structs and f['arr'] == 1:
                cur = self.follow_dynamics(base, fo, cur, ctx, depth)
                continue
            if not f.get('is_ptr'):
                continue
            marker = self.u32(fo)
            if not self.eval_cond(d.get('condition'), ctx):
                continue
            if marker == 0 or (marker != FOLLOW and marker != INSERT):
                continue  # null or alias (already-written) -> no inline data
            if d.get('string'):
                cur = self.skip_cstring(cur); continue
            if d.get('assetref'):
                continue
            count = self.eval_count(d['count'], ctx) if d.get('count') else 1
            if count <= 0:
                continue
            cur = self._read_array(base, count, cur, depth)
        return cur

    def _read_array(self, base, count, cur, depth):
        """Advance past `count` elements of `base`. Array order: ALL bodies first,
        then each element's dynamic data (matches OAT's array serialization)."""
        if count > 2_000_000 or depth > 64:
            # suspect count (e.g. streamed GX2 shader program mis-sized on console):
            # skip this follow rather than abort the whole asset.
            self.errors.append("skip count=%d depth=%d %s" % (count, depth, base))
            return cur
        if base in self.L.structs:
            s = self.gs(base)
            has_dyn = any(self.zc.d.get(base, {}).get(f['name'], {}).get('string')
                          or self.zc.d.get(base, {}).get(f['name'], {}).get('count')
                          or f.get('is_ptr')
                          or (f['base'] in self.L.structs and not f.get('is_ptr'))
                          for f in s['fields'] if 'error' not in f)
            array_start = cur
            cur += count * s['size']            # all element bodies
            if has_dyn:
                for i in range(count):
                    cur = self.follow_dynamics(base, array_start + i*s['size'], cur, {}, depth+1)
            return cur
        sz, _ = self.L._resolve(base)
        return cur + count * sz


def main():
    zpath = sys.argv[1] if len(sys.argv) > 1 else 'mp_raid_genuine.zone'
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    import importlib
    wz = importlib.import_module('wiiu_zone')
    zone = open(zpath, 'rb').read()
    r = wz.ZoneReader(zone); r.read_string_table(); r.read_asset_list()
    L = struct_layout.Layout(HDR, console=True)
    zc = ZoneCode(ZC_DIR)
    w = Walker(zone, L, zc, r.block_sizes)
    def next_body(nm_next, frm, window=8192):
        """Find where asset[i+1] (type nm_next) really starts, at/after frm.
        Returns (offset, gap) using type-aware validation, or (None, 0)."""
        root_next = ASSET_ROOT.get(nm_next)
        if root_next is None:
            return None, 0
        o = frm
        for g in range(0, window, 4):
            if w.is_plausible_body(root_next, o + g):
                return o + g, g
        return None, 0

    from collections import defaultdict
    cur = r.assets_end
    clean = 0
    gaps = defaultdict(list)     # (walked_type -> observed gap sizes before next asset)
    lost = 0
    for i, (cid, pc, nm) in enumerate(r.assets):
        root = ASSET_ROOT.get(nm)
        start = cur
        if root is None or root not in L.structs:
            cur = start; nxt = None
        else:
            try:
                cur = w.walk(root, cur)
            except Exception:
                cur = start
        # verify against the NEXT asset's expected body (ground-truth resync)
        if i < len(r.assets) - 1:
            nm_next = r.assets[i+1][2]
            pos, gap = next_body(nm_next, cur)
            if pos is None:
                lost += 1
                if limit and i < limit:
                    print("  [%d] %-16s 0x%07x -> 0x%07x  next(%s) NOT FOUND" %
                          (i, nm, start, cur, nm_next))
                # give up precise tracking once lost
                break
            if gap == 0:
                clean += 1
            else:
                gaps[nm].append(gap)
            if limit and i < limit:
                mark = "" if gap == 0 else "  GAP=%d" % gap
                print("  [%d] %-16s 0x%07x -> 0x%07x (walk+%d) next@0x%07x%s" %
                      (i, nm, start, cur, cur-start, pos, mark))
            cur = pos
        else:
            clean += 1
    print("\nresynced cleanly through %d assets (lost after: %s)" %
          (clean + sum(len(v) for v in gaps.values()), "yes" if lost else "no"))
    print("assets with a trailing gap (walked_type: gap sizes):")
    for k, v in sorted(gaps.items(), key=lambda x: -len(x[1]))[:20]:
        from collections import Counter
        print("  %-18s x%d  gaps=%s" % (k, len(v), dict(Counter(v))))


if __name__ == '__main__':
    main()
