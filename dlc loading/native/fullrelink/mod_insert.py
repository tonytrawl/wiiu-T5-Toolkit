#!/usr/bin/env python3
"""
Insert/replace LUI rawfiles with loose SOURCE .lua (tests whether the WiiU engine's
hksL_loadfile compiles ff-baked source at load). Reuses ui_splice.rebuild machinery.

  python mod_insert.py <ff-basename> <asset-name>=<source.lua> [more...]
e.g. python mod_insert.py patch_ui_mp ui/t6/mainlobby.lua=<path to modded mainlobby>
"""
import sys, os, struct
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import ui_splice as US
import wiiu_ff

FOLLOW = 0xFFFFFFFF
MOD = os.path.join(US._ROOT, 'mod_loader_patch', 'content_root')


def load_stock(fn):
    stock = US.SRC + fn + '.stockbak'
    p = stock if os.path.exists(stock) else US.SRC + fn
    return wiiu_ff.decrypt(open(p, 'rb').read())[1]


def main():
    ff_base = sys.argv[1]                       # e.g. patch_ui_mp
    repl = {}
    for a in sys.argv[2:]:
        name, path = a.split('=', 1)
        repl[name] = path
    fn = ff_base + '.ff'
    wz = load_stock(fn)
    Wsp = US.rawfile_spans(wz, True)
    subs = {}
    for name, path in repl.items():
        if name not in Wsp:
            raise SystemExit('asset %r not found in %s (insertion of NEW asset not yet supported here)' % (name, fn))
        H, boff, oldlen, nmb = Wsp[name]
        src = open(path, 'rb').read()
        trail = wz[boff+oldlen:boff+oldlen+1]
        assert trail == b'\x00', ('%s trailing %r' % (name, trail))
        new_body = struct.pack('>III', FOLLOW, len(src), FOLLOW) + nmb + b'\x00' + src + b'\x00'
        subs[H] = (boff + oldlen + 1, new_body)
        print('  %-28s old=%d bytes -> SOURCE %d bytes' % (name, oldlen, len(src)))
    edited, td, nhp = US.rebuild(wz, subs)
    ff = wiiu_ff.pack(edited, ff_base)
    _h, z2, _n = wiiu_ff.decrypt(ff)
    outdir = os.path.join(US._ROOT, 'dlc loading', 'native', 'fullrelink', '_mod_insert')
    os.makedirs(outdir, exist_ok=True)
    outp = os.path.join(outdir, fn)
    open(outp, 'wb').write(ff)
    print('rebuilt %s: +%d zone, %d relinked, repack-matches=%s -> %s'
          % (fn, td, nhp, z2 == edited, outp))


if __name__ == '__main__':
    main()
