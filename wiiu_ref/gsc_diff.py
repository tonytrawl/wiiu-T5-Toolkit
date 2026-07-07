#!/usr/bin/env python3
"""
T6 compiled GSC (GSCOBJ) parser + PC(x86 LE) -> Wii U(PPC BE) transcoder.

Format (offsets into the script buffer; endianness = platform endianness):
  header 0x40 bytes:
    +0x00 char magic[8] = 80 47 53 43 0D 0A 00 06  ("\x80GSC\r\n\0\x06")
    +0x08 u32 source_crc
    +0x0C u32 include_offset      +0x10 u32 animtree_offset
    +0x14 u32 cseg_offset         +0x18 u32 stringtablefixup_offset
    +0x1C u32 exports_offset      +0x20 u32 imports_offset
    +0x24 u32 fixup_offset        +0x28 u32 profile_offset
    +0x2C u32 cseg_size
    +0x30 u16 name (offset of script path string)
    +0x32 u16 stringtablefixup_count  +0x34 u16 exports_count
    +0x36 u16 imports_count           +0x38 u16 fixup_count
    +0x3A u16 profile_count
    +0x3C u8 include_count  +0x3D u8 animtree_count  +0x3E u8 flags  +0x3F pad
  strings: NUL-terminated, immediately after header. Identical bytes on both
  platforms.
  include table: include_count * u32 (string offsets).
  animtree table: animtree_count * { u16 name, u16 num_address,
    then num_address * u32 patch addresses } (addresses point at the aligned
    u32 operand of GetAnimation/GetAnimTree in cseg).
  exports: exports_count * { u32 checksum, u32 address, u16 name,
    u8 param_count, u8 flags } (12 bytes).
  imports: imports_count * { u16 name, u16 name_space, u16 num_address,
    u8 param_count, u8 flags, then num_address * u32 } (addresses point at the
    CALL OPCODE byte, not its operand).
  stringtablefixup: count * { u16 string, u8 num_address, u8 type,
    then num_address * u32 } (addresses point at the aligned u16 operand of
    GetString/GetIString).
  cseg: the opcode stream. One opcode = 1 byte, identical numeric values on
  both platforms. Multi-byte operands are aligned to their size RELATIVE TO
  BUFFER START and are stored in platform endianness (that is the entire
  cseg delta). Each function is preceded by a 6-byte prefix
  { u16 unknown, u32 zero } that is NOT byte-swapped (raw bytes) and the
  function start (export address) is 4-aligned.

PC -> console transform (pc_gsc_to_console): byte-swap the header words, every
table field, and every multi-byte cseg operand, walking the opcode stream from
each export address. Opcodes, strings, u8 operands and the 6-byte function
prefixes are copied verbatim. Verified byte-exact against every genuine Wii U
script paired with its PC twin (see main()).
"""
import struct, sys, os

MAGIC = b'\x80GSC\x0d\x0a\x00\x06'

# ---------------------------------------------------------------- header

HDR_KEYS = ['crc', 'include_off', 'animtree_off', 'cseg_off', 'stf_off',
            'exports_off', 'imports_off', 'fixup_off', 'profile_off',
            'cseg_size', 'name', 'stf_count', 'exports_count',
            'imports_count', 'fixup_count', 'profile_count',
            'include_count', 'animtree_count', 'flags']


def parse_header(d, e):
    assert d[:8] == MAGIC, 'bad GSC magic'
    vals = struct.unpack(e + '8xI8II6H2BBx', d[:0x40])
    return dict(zip(HDR_KEYS, vals))


# ------------------------------------------------- opcode operand table
# Operand spec tokens, applied in order after the 1-byte opcode:
#   u8            1 raw byte (no swap)
#   u16 / u32     align to 2/4 (buffer-absolute), swap 2/4 bytes
#   vec3          align 4, swap 3 consecutive u32
#   lvars         SafeCreateLocalVariables payload
#   switch        EndSwitch jump table payload
# Opcode numbers are the T6 set, identical on PC and Wii U (verified).
OPS = {}


def _op(rng, spec):
    if isinstance(rng, int):
        rng = [rng]
    for k in rng:
        OPS[k] = spec


_op(0x00, [])            # End
_op(0x01, [])            # Return
_op(0x02, [])            # GetUndefined
_op(0x03, [])            # GetZero
_op(0x04, ['u8'])        # GetByte
_op(0x05, ['u8'])        # GetNegByte
_op(0x06, ['u16'])       # GetUnsignedShort
_op(0x07, ['u16'])       # GetNegUnsignedShort
_op(0x08, ['u32'])       # GetInteger
_op(0x09, ['u32'])       # GetFloat
_op(0x0A, ['u16'])       # GetString (stringtablefixup target, type 0)
_op(0x0B, ['u16'])       # GetIString
_op(0x0C, ['vec3'])      # GetVector
_op(list(range(0x0D, 0x13)), [])   # GetLevelObject..GetGame etc. (no operand)
_op(0x13, ['u32'])       # GetAnimTree (animtree fixup target)
_op(0x14, [])
_op(0x15, ['u32'])       # GetFunction (import target, aligned u32)
_op(0x16, ['u32'])
_op(0x17, ['lvars'])     # SafeCreateLocalVariables: u8 n, n x align2 u16 name
_op(0x18, ['u8'])
_op(0x19, ['u8'])        # EvalLocalVariableCached
_op(0x1A, [])            # EvalArray
_op(0x1B, [])            # EvalArray
_op(0x1C, [])            # EvalArrayRef
_op(0x1D, [])            # ClearArray
_op(0x1E, [])            # EmptyArray
_op(0x1F, [])            # GetSelfObject
_op(0x20, ['u16'])       # EvalFieldVariable (string-offset operand, stf type 1)
_op(0x21, ['u16'])       # EvalFieldVariableRef (string-offset operand)
_op(0x22, ['u16'])       # ClearFieldVariable
_op(0x23, [])
_op(0x24, ['u8'])
_op(0x25, [])
_op(0x26, [])            # CheckClearParams
_op(0x27, ['u8'])        # EvalLocalVariableRefCached
_op(0x28, [])            # SetVariableField
_op(0x29, [])
_op(0x2A, ['u16'])       # CallBuiltin (builtin function index)
_op(0x2B, [])
_op(0x2C, [])            # Wait
_op(0x2D, [])            # PreScriptCall
_op(0x2E, ['u8', 'u32'])  # ScriptFunctionCall: u8, then aligned u32 (import)
_op(0x2F, [])            # ScriptFunctionCallPointer
_op(0x30, ['u8', 'u32'])  # ScriptMethodCall (import)
_op(0x31, [])            # ScriptMethodCallPointer
_op(0x32, ['u8', 'u32'])  # ScriptThreadCall (import)
_op(0x33, [])            # ScriptThreadCallPointer
_op(0x34, ['u8', 'u32'])  # ScriptMethodThreadCall (import)
_op(0x35, [])            # ScriptMethodThreadCallPointer
_op(0x36, [])            # DecTop
_op(0x37, [])            # CastFieldObject
_op(0x38, [])            # CastBool
_op(0x39, [])            # BoolNot
_op(0x3A, [])            # BoolComplement
_op(0x3B, ['u16'])       # JumpOnFalse (rel16)
_op(0x3C, ['u16'])       # JumpOnTrue
_op(0x3D, ['u16'])       # JumpOnFalseExpr
_op(0x3E, ['u16'])       # JumpOnTrueExpr
_op(0x3F, ['u16'])       # Jump (rel16, backward jumps seen)
_op(0x40, ['u16'])       # JumpBack
_op(0x41, [])            # Inc
_op(0x42, [])            # Dec
_op(list(range(0x43, 0x59)), [])   # arithmetic/compare block (no operand)
_op(0x59, ['u32'])
_op(0x5A, ['switch'])    # Switch -> u32 rel, then EndSwitch table
_op(0x5B, [])            # Vector (builds vec3 from stack)
_op(0x5C, ['u32'])       # GetHash (aligned u32)
_op(0x5D, [])
_op(0x5E, ['u8'])        # (cached-variable op, u8 index)
_op(0x5F, [])
_op(0x60, [])
_op(0x61, [])
_op(0x62, [])
_op(list(range(0x63, 0x7B)), [])   # no-operand ops (0x69/0x70/0x71 seen)
_op(0x7B, ['u16'])
_op(list(range(0x7C, 0x98)), [])   # default no-operand tail


class OpErr(Exception):
    pass


def _align(o, n):
    return (o + n - 1) & ~(n - 1)


def swap_cseg(src, out, h, e_src):
    """Walk the opcode stream function by function, byte-swapping operands
    in place in `out` (a bytearray copy of src). Returns list of
    (offset, size) swapped for diagnostics."""
    exports = []
    eo = h['exports_off']
    for i in range(h['exports_count']):
        crc, addr, nm, pc_, fl = struct.unpack_from(e_src + 'IIHBB', src, eo + 12*i)
        exports.append(addr)
    exports.sort()
    cend = h['cseg_off'] + h['cseg_size']
    swaps = []

    def swp(o, n):
        out[o:o+n] = src[o:o+n][::-1]
        swaps.append((o, n))

    for fi, fstart in enumerate(exports):
        nxt = exports[fi+1] if fi + 1 < len(exports) else None
        o = fstart
        while True:
            if nxt is not None:
                # a function is preceded by garbage pad to a 4-byte boundary
                # plus one zero u32; once we can only be inside that prefix,
                # the function is done
                if _align(o, 4) + 4 >= nxt:
                    break
            elif o >= cend:
                break
            op = src[o]
            spec = OPS.get(op)
            if spec is None:
                ctx = ' '.join('%02x' % x for x in src[max(0, o-12):o+12])
                raise OpErr('unknown opcode 0x%02x at 0x%x (func @0x%x) '
                            'ctx[-12:+12]=%s' % (op, o, fstart, ctx))
            o += 1
            for t in spec:
                if t == 'u8':
                    o += 1
                elif t == 'u16':
                    o = _align(o, 2); swp(o, 2); o += 2
                elif t == 'u32':
                    o = _align(o, 4); swp(o, 4); o += 4
                elif t == 'vec3':
                    o = _align(o, 4)
                    for _ in range(3):
                        swp(o, 4); o += 4
                elif t == 'lvars':
                    cnt = src[o]; o += 1
                    for _ in range(cnt):
                        o = _align(o, 2); swp(o, 2); o += 2  # var name str off
                elif t == 'switch':
                    o = _align(o, 4)
                    cnt = struct.unpack_from(e_src + 'I', src, o)[0]
                    swp(o, 4); o += 4
                    if cnt > 0x10000:
                        raise OpErr('implausible switch count %d at 0x%x'
                                    % (cnt, o - 4))
                    for _ in range(cnt):
                        swp(o, 4); o += 4     # case value / string offset
                        swp(o, 4); o += 4     # relative jump

                else:
                    raise OpErr('bad spec token ' + t)
    return swaps


def pc_gsc_to_console(buf):
    """Transform a PC (little-endian) compiled GSC buffer into the Wii U
    (big-endian) encoding. Returns bytes of identical length."""
    return _transcode(buf, '<', '>')


def console_gsc_to_pc(buf):
    return _transcode(buf, '>', '<')


def _transcode(buf, e_src, e_dst):
    d = bytes(buf)
    h = parse_header(d, e_src)
    out = bytearray(d)

    def rewrite(o, fmt):
        vals = struct.unpack_from(e_src + fmt, d, o)
        struct.pack_into(e_dst + fmt, out, o, *vals)

    # header
    rewrite(0x08, 'I8II6H')
    # include table
    rewrite(h['include_off'], '%dI' % h['include_count'])
    # animtree table
    o = h['animtree_off']
    for _ in range(h['animtree_count']):
        nm, z0, cnt, z1 = struct.unpack_from(e_src + '4H', d, o)
        rewrite(o, '4H'); o += 8
        rewrite(o, '%dI' % (2 * cnt)); o += 8 * cnt   # {name_off, addr} pairs
    # exports
    o = h['exports_off']
    for _ in range(h['exports_count']):
        rewrite(o, 'IIH'); o += 12          # trailing u8 pair untouched
    # imports
    o = h['imports_off']
    for _ in range(h['imports_count']):
        nm, ns, cnt = struct.unpack_from(e_src + 'HHH', d, o)
        rewrite(o, 'HHH'); o += 8           # +u8 params +u8 flags
        rewrite(o, '%dI' % cnt); o += 4 * cnt
    # stringtablefixup
    o = h['stf_off']
    for _ in range(h['stf_count']):
        s, cnt, typ = struct.unpack_from(e_src + 'HBB', d, o)
        rewrite(o, 'H'); o += 4             # count/type are u8s
        rewrite(o, '%dI' % cnt); o += 4 * cnt
    # fixups / profile (never populated in shipped zones; swap generically)
    o = h['fixup_off']
    for _ in range(h['fixup_count']):
        rewrite(o, 'II'); o += 8
    # cseg operands
    swap_cseg(d, out, h, e_src)
    # export checksums: checksum = zlib.crc32(function code bytes, 0), where
    # the code range starts at the export address and ends before the
    # garbage pad + zero-word prefix of the next function. The exact code
    # length is recovered by matching the SOURCE checksum against crc32 of
    # every prefix length, then the same length of the swapped bytes is
    # hashed for the destination platform.
    import zlib
    entries = []
    eo = h['exports_off']
    for i in range(h['exports_count']):
        crc, addr, nm, pc_, fl = struct.unpack_from(e_src + 'IIHBB', d,
                                                    eo + 12*i)
        entries.append((addr, crc, eo + 12*i))
    bounds = sorted(a for a, _, _ in entries) + [h['cseg_off'] + h['cseg_size']]
    for addr, crc, ent_off in entries:
        hi = min(b for b in bounds if b > addr)
        c = 0
        ln = None
        for L in range(0, hi - addr + 1):
            if c == crc:
                ln = L        # keep last match; zero-length prefix matches 0
                if L and crc != 0:
                    break
            if addr + L < hi:
                c = zlib.crc32(d[addr+L:addr+L+1], c) & 0xffffffff
        if ln is None:
            raise OpErr('export checksum at 0x%x does not match any code '
                        'prefix crc32' % ent_off)
        new = zlib.crc32(bytes(out[addr:addr+ln])) & 0xffffffff
        struct.pack_into(e_dst + 'I', out, ent_off, new)
    return bytes(out)


# ---------------------------------------------------------------- driver

def load_scripts(zone_path):
    from scriptparsetree_probe import find_spt, parse_spt, detect_endian
    d = open(zone_path, 'rb').read()
    e = detect_endian(d)
    return {n: parse_spt(d, b, e)[2] for b, n, ln, buf in find_spt(d, e)}, e


def main():
    wu_zone = sys.argv[1] if len(sys.argv) > 1 else 'mp_raid_genuine.zone'
    pc_zone = sys.argv[2] if len(sys.argv) > 2 else '../PC ff/mp_raid.zone'
    wu, _ = load_scripts(wu_zone)
    pc, _ = load_scripts(pc_zone)
    names = sorted(set(wu) & set(pc))
    print('paired scripts: %d (wu-only=%d pc-only=%d)' %
          (len(names), len(set(wu)-set(pc)), len(set(pc)-set(wu))))
    exact = 0
    for n in names:
        try:
            got = pc_gsc_to_console(pc[n])
        except OpErr as ex:
            print('  FAIL %-52s %s' % (n, ex))
            continue
        if got == wu[n]:
            exact += 1
            print('  OK   %-52s len=%d byte-exact' % (n, len(got)))
        else:
            bad = [i for i in range(len(got)) if got[i] != wu[n][i]]
            print('  DIFF %-52s %d bytes differ, first at 0x%x' %
                  (n, len(bad), bad[0]))
            for i in bad[:6]:
                print('        0x%06x got=%02x want=%02x pc=%02x' %
                      (i, got[i], wu[n][i], pc[n][i]))
    print('byte-exact: %d / %d' % (exact, len(names)))


if __name__ == '__main__':
    main()
