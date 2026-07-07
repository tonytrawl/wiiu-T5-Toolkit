#!/usr/bin/env python3
"""
GSC injection for a ported map: find every SCRIPTPARSETREE buffer in a
console (big-endian) zone image that still holds PC-endian GSC and transcode
it in place with gsc_diff.pc_gsc_to_console().

Why in-place works: the ScriptParseTree asset is PC-identical (12 B body:
name ptr, len, buffer ptr; consume strlen(name)+1 then len+1 buffer bytes,
see scriptparsetree_probe.py) and pc_gsc_to_console() is byte-length
preserving (verified byte-exact 43/43 against genuine Wii U scripts in
gsc_diff.py). So script injection is a pure payload swap: no offsets,
pointers, or asset sizes move.

API:
  find_spt_buffers(zone_bytes)          -> [(body_off, name, buf_off, len)]
  inject(zone_bytes)                    -> (new_bytes, report)
      transcodes every SPT buffer whose GSC header is little-endian (PC);
      buffers already big-endian (console) are left untouched, so the tool
      is idempotent and safe on mixed zones.
  CLI: python gsc_inject.py <zone-in> [zone-out]
      without zone-out: dry run, prints what would be transcoded.

Verification (run: python gsc_inject.py --selftest):
  1. Genuine Wii U zones (mp_raid_genuine, zm_transit_original): every SPT is
     detected, none is misclassified as PC (zero rewrites, output byte-exact).
  2. Round trip on genuine Wii U buffers: console->pc->console byte-exact for
     every SPT in both zones.
  3. Synthetic injection: take a genuine Wii U zone, convert every SPT buffer
     to PC endianness (console_gsc_to_pc) to fake a ported-from-PC zone, run
     inject(), output equals the genuine zone byte-exact.
"""
import struct
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gsc_diff import pc_gsc_to_console, console_gsc_to_pc, parse_header

FOLLOW = b'\xff\xff\xff\xff'
NAME_RE = re.compile(rb'[\w/.\-]+\.(gsc|csc)$')
GSC_MAGIC = b'\x80GSC'


def _hdr_plausible(buf, e):
    """All GSCOBJ header offsets in range and ordered for endianness e."""
    try:
        h = parse_header(buf, e)
    except Exception:
        return False
    offs = [h['include_off'], h['animtree_off'], h['cseg_off'], h['stf_off'],
            h['exports_off'], h['imports_off'], h['fixup_off'],
            h['profile_off']]
    if any(o < 0x40 or o > len(buf) for o in offs):
        return False
    return h['cseg_off'] + h['cseg_size'] <= len(buf)


def _gsc_is_le(buf):
    """True if a GSC buffer is little-endian (PC)."""
    le, be = _hdr_plausible(buf, '<'), _hdr_plausible(buf, '>')
    if le == be:
        raise ValueError('cannot determine GSC endianness (le=%s be=%s)'
                         % (le, be))
    return le


def find_spt_buffers(d):
    """Locate every serialized ScriptParseTree in a zone image.
    A body is: FOLLOW name ptr, u32 len, FOLLOW buffer ptr, then the inline
    name (a .gsc/.csc path) and the len+1 byte buffer starting with 80 GSC.
    len is read with the endianness that matches the name length, so the
    scan works on both BE console zones and LE PC zones."""
    out = []
    pos = 0
    n = len(d)
    while True:
        pos = d.find(FOLLOW, pos)
        if pos < 0:
            break
        b = pos
        pos += 1
        if d[b + 8:b + 12] != FOLLOW:
            continue
        nul = d.find(b'\x00', b + 12, b + 12 + 128)
        if nul < 0:
            continue
        if not NAME_RE.fullmatch(d[b + 12:nul]):
            continue
        buf = nul + 1
        if d[buf:buf + 4] != GSC_MAGIC:
            continue
        ln = None
        for e in ('>', '<'):
            cand = struct.unpack(e + 'I', d[b + 4:b + 8])[0]
            if 8 <= cand < 0x400000 and buf + cand < n and d[buf + cand] == 0:
                ln = cand
                break
        if ln is None:
            continue
        out.append((b, d[b + 12:nul].decode(), buf, ln))
    return out


def inject(d, transcode=pc_gsc_to_console, want_le_input=True):
    """Return (bytes, report). Applies `transcode` to every SPT buffer whose
    endianness matches want_le_input (default: PC buffers -> console)."""
    out = bytearray(d)
    report = []
    for b, name, buf, ln in find_spt_buffers(d):
        body = bytes(d[buf:buf + ln])
        is_le = _gsc_is_le(body)
        if is_le != want_le_input:
            report.append((name, ln, 'skip (already target endianness)'))
            continue
        swapped = transcode(body)
        if len(swapped) != ln:
            raise ValueError('%s: transcode changed length %d -> %d'
                             % (name, ln, len(swapped)))
        out[buf:buf + ln] = swapped
        report.append((name, ln, 'transcoded'))
    return bytes(out), report


def _selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    zones = [os.path.join(here, z) for z in
             ('mp_raid_genuine.zone', 'zm_transit_original.zone')]
    for zp in zones:
        d = open(zp, 'rb').read()
        spts = find_spt_buffers(d)
        assert spts, 'no SPTs found in %s' % zp

        # 1. a genuine console zone must pass through inject() unchanged
        out, report = inject(d)
        changed = [r for r in report if r[2] == 'transcoded']
        assert out == d and not changed, \
            '%s: genuine zone was modified' % zp

        # 2. console -> pc -> console round trip, byte-exact per buffer
        rt_ok = 0
        for b, name, buf, ln in spts:
            body = d[buf:buf + ln]
            back = pc_gsc_to_console(console_gsc_to_pc(body))
            assert back == body, '%s: round trip mismatch in %s' % (zp, name)
            rt_ok += 1

        # 3. synthetic ported zone: PC-endian buffers, then inject
        fake = bytearray(d)
        for b, name, buf, ln in spts:
            fake[buf:buf + ln] = console_gsc_to_pc(d[buf:buf + ln])
        fixed, report = inject(bytes(fake))
        n_tc = sum(1 for r in report if r[2] == 'transcoded')
        assert fixed == d, '%s: injected zone != genuine zone' % zp
        assert n_tc == len(spts)

        print('%s: %d SPTs; genuine untouched; round trip %d/%d; '
              'synthetic PC zone injected -> byte-exact vs genuine'
              % (os.path.basename(zp), len(spts), rt_ok, len(spts)))
    print('ALL CHECKS PASSED')


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == '--selftest':
        _selftest()
        return
    if len(sys.argv) < 2:
        print(__doc__)
        return
    d = open(sys.argv[1], 'rb').read()
    out, report = inject(d)
    for name, ln, action in report:
        print('  %-60s %7d  %s' % (name, ln, action))
    n_tc = sum(1 for r in report if r[2] == 'transcoded')
    print('%d SPT buffers, %d transcoded' % (len(report), n_tc))
    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'wb') as f:
            f.write(out)
        print('wrote', sys.argv[2])
    elif n_tc:
        print('(dry run: pass an output path to write)')


if __name__ == '__main__':
    main()
