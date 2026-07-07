#!/usr/bin/env python3
"""Validate the XModel *body* PC->console converter (HANDOFF Track C) vs genuine common_mp.

Matched-pair oracle (like validate_material): console XModel bodies via xmodel_probe.is_body /
parse_xmodel, joined to PC bodies by model-name string. The converter's 244 B body must equal the
genuine console body once the two non-PC-derivable fields (himipInvSqRadii ptr @200, memUsage @204)
and the relocated pointer words are masked (pointer alias values are platform-specific).
"""
import struct, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import xmodel_probe as XP
import xmodel_convert as XC

CO_PATH = os.path.join('..', 'common_mp.zone')
PC_PATH = os.path.join('..', 'PC ff', 'common_mp.zone')

# console body pointer-word offsets (name + 8 members + collSurfs/boneInfo + shifted tail ptrs)
PTR_OFFS = (0, 8, 12, 16, 20, 24, 28, 32, 36, 152, 164, 212, 220, 224)
COMPUTED = (200, 204)   # himipInvSqRadii ptr, memUsage


def enum_console(CO):
    co = {}
    i = 0
    while i < len(CO) - XC.CO_BODY:
        j = CO.find(b'\xff\xff\xff\xff', i)
        if j < 0:
            break
        if XP.is_body(CO, j, strict=True):
            try:
                _, name = XP.parse_xmodel(CO, j)
                if name and not name.startswith('<'):
                    co.setdefault(name, j)
            except Exception:
                pass
        i = j + 4
    return co


def match_pairs(PC, CO):
    pairs = []
    for nm, cs in enum_console(CO).items():
        p = PC.find(nm.encode('latin-1') + b'\x00')
        while p >= 0:
            pb = p - XC.PC_BODY
            if (pb >= 0 and struct.unpack_from('<I', PC, pb)[0] == XC.FOLLOW
                    and PC[pb + 4] == CO[cs + 4] and PC[pb + 6] == CO[cs + 6]):
                pairs.append((nm, pb, cs)); break
            p = PC.find(nm.encode('latin-1') + b'\x00', p + 1)
    return pairs


def mask(b):
    b = bytearray(b[:XC.CO_BODY])
    for o in PTR_OFFS + COMPUTED:
        b[o:o + 4] = b'\x00\x00\x00\x00'
    return bytes(b)


def main():
    CO = open(CO_PATH, 'rb').read()
    PC = open(PC_PATH, 'rb').read()
    pairs = match_pairs(PC, CO)
    print("matched XModel pairs: %d\n" % len(pairs))
    ok = bad = 0
    fails = []
    for nm, pb, cs in pairs:
        out = XC.convert_xmodel_body(PC, pb)
        if mask(out) == mask(CO[cs:cs + XC.CO_BODY]):
            ok += 1
        else:
            bad += 1
            mo, mg = mask(out), mask(CO[cs:cs + XC.CO_BODY])
            d = [j for j in range(XC.CO_BODY) if mo[j] != mg[j]]
            if len(fails) < 12:
                fails.append((nm, d[:6]))
    print("BODY (masked ptrs + computed fields) vs genuine console: %d exact, %d differ" % (ok, bad))
    for nm, d in fails:
        print("   %-32s diff at %s" % (nm, d))
    # report memUsage: how far off is a naive PC copy? (context for Track G)
    print("\n(reminder: himipInvSqRadii @200 + memUsage @204 are console-computed — masked here,")
    print(" must be synthesized at integration; all other body fields are byte-exact from PC.)")

    # ---- bone-data block (name..baseMat, precedes surfaces) ----
    bd_ok = bd_bad = 0
    bfails = []
    for nm, pb, cs in pairs:
        conv, _ = XC.convert_xmodel_bonedata(PC, pb)
        genuine = CO[cs + XC.CO_BODY: cs + XC.CO_BODY + len(conv)]
        if conv == genuine:
            bd_ok += 1
        else:
            bd_bad += 1
            if len(bfails) < 10:
                d = next((j for j in range(min(len(conv), len(genuine))) if conv[j] != genuine[j]), 'len')
                bfails.append((nm, d, len(conv), len(genuine)))
    print("\nBONE-DATA block (name/boneNames/parentList/quats/trans/partClass/baseMat) vs genuine: "
          "%d exact, %d differ" % (bd_ok, bd_bad))
    for f in bfails:
        print("   %-32s first-diff %s (conv %d / gen %d)" % f)


if __name__ == '__main__':
    main()
