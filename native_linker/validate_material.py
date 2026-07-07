#!/usr/bin/env python3
"""Validate the Material PC->console converter (HANDOFF Track A) against genuine common_mp.

common_mp is the shared-asset zone that actually contains Material assets (map zones like
mp_raid alias them and hold NONE). We build a matched-pair oracle: materials that appear in
BOTH PC and console common_mp, joined by their info.name string, then:

  * convert the real PC body and compare to the genuine console body (masked pointers, since
    alias values are platform-specific), and
  * round-trip genuine console bodies (console -> PC -> console) for self-consistency.

Complete-name matching (name preceded by NUL, FOLLOW header, counts agree) avoids the
substring collisions that plague a naive name scan (e.g. 'm_b0c0_x' inside 'mc_lit_sm_b0c0_x').
"""
import struct, os, re
import material_convert as MC

CO_PATH = os.path.join('..', 'common_mp.zone')
PC_PATH = os.path.join('..', 'PC ff', 'common_mp.zone')
NAME = re.compile(rb'[A-Za-z][A-Za-z0-9_/]{4,60}\x00')
FOLLOW = 0xFFFFFFFF


def _valid_ptr(v):
    return v == FOLLOW or v == 0 or 0xA0000000 <= v < 0xF0000000


def matched_pairs(PC, CO):
    """Return [(name, pc_body_off, console_body_off)] for complete-name materials in both zones."""
    cand = {}
    i = 0
    while True:
        i = PC.find(b'\xff\xff\xff\xff', i)
        if i < 0:
            break
        m = NAME.match(PC, i + MC.PC_MAT_SIZE)
        if (m and PC[i + 84] < 64 and PC[i + 85] < 64 and PC[i + 86] < 64
                and PC[i + MC.PC_MAT_SIZE - 1] == 0                      # name complete (prev byte NUL)
                and _valid_ptr(struct.unpack_from('<I', PC, i + 92)[0])):
            cand.setdefault(m.group()[:-1].decode('latin-1'), i)
        i += 4
    pairs = []
    for nm, pb in cand.items():
        npos = CO.find(nm.encode('latin-1') + b'\x00')
        if npos < 0 or CO[npos - 1] != 0:
            continue
        cs = npos - MC.CO_MAT_SIZE
        if cs < 0 or struct.unpack_from('>I', CO, cs)[0] != FOLLOW:
            continue
        if CO[cs + 72:cs + 75] != PC[pb + 84:pb + 87]:      # texture/constant/statebits counts agree
            continue
        pairs.append((nm, pb, cs))
    return pairs


def _has_inline_image(CO, cs):
    """True if the console material at cs carries an INLINE image (a texture def whose image ptr is
    FOLLOW/INSERT). deconvert_material re-emits only the image pointer, not the console GfxImage body,
    so such materials cannot self-round-trip — TEST 1 already excludes them from byte validation, and
    TEST 2 must too (otherwise convert_material walks pc_image_span past the reconstructed buffer)."""
    PTRS = (0xFFFFFFFF, 0xFFFFFFFE)
    texc = CO[cs + 72]
    name_p = struct.unpack_from('>I', CO, cs + 0)[0]    # info.name ptr (console @0)
    tt = struct.unpack_from('>I', CO, cs + 84)[0]       # textureTable ptr (console @84)
    src = cs + MC.CO_MAT_SIZE
    if name_p in PTRS:                                   # info.name c-string
        src = CO.index(b'\x00', src) + 1
    if tt not in PTRS:
        return False
    for i in range(texc):
        if struct.unpack_from('>I', CO, src + i * MC.TEXDEF_SIZE + 12)[0] in PTRS:
            return True
    return False


def _mask_body(b):
    """104-byte console body with pointer words zeroed (name + 5 body pointers)."""
    b = bytearray(b[:MC.CO_MAT_SIZE])
    for o in (0, 80, 84, 88, 92, 96):
        b[o:o + 4] = b'\x00\x00\x00\x00'
    return bytes(b)


def main():
    CO = open(CO_PATH, 'rb').read()
    PC = open(PC_PATH, 'rb').read()
    pairs = matched_pairs(PC, CO)
    print("matched-pair oracle: %d materials shared by PC & console common_mp\n" % len(pairs))

    # ---- TEST 1: true oracle (masked body) ----
    ok = bad = 0
    sbe = 0                      # diffs confined to stateBitsEntry (technique 36->32 remap)
    other = []
    for nm, pb, cs in pairs:
        out, _ = MC.convert_material(PC, pb)
        mo, mg = _mask_body(out), _mask_body(CO[cs:cs + MC.CO_MAT_SIZE])
        if mo == mg:
            ok += 1
            continue
        bad += 1
        diffs = [j for j in range(MC.CO_MAT_SIZE) if mo[j] != mg[j]]
        if all(40 <= j < 72 for j in diffs):
            sbe += 1
        elif len(other) < 10:
            other.append((nm, diffs))
    print("TEST 1  body vs genuine console: %d exact, %d differ  (%d only in stateBitsEntry)"
          % (ok, bad, sbe))
    for nm, d in other:
        print("   diff %-40s at %s" % (nm, d))

    # ---- TEST 2: round-trip (console -> PC -> console) ----
    # Restricted to PURE materials (no inline image): those with trailing state-bits/texture/constant
    # tables round-trip fully; inline-image materials can't (deconvert re-emits only the image ptr,
    # not the console GfxImage body — same exclusion TEST 1 applies to byte validation).
    rt_ok = rt_bad = 0
    rt_pure = 0
    for nm, pb, cs in pairs:
        if _has_inline_image(CO, cs):
            continue
        rt_pure += 1
        genuine = CO[cs:cs + MC.CO_MAT_SIZE]
        pc_bytes, _ = MC.deconvert_material(CO, cs)
        back, _ = MC.convert_material(pc_bytes, 0)
        # round-trip reproduces the 104-byte body (trailing tables need the same body pointers)
        if back[:MC.CO_MAT_SIZE] == genuine:
            rt_ok += 1
        else:
            rt_bad += 1
    print("\nTEST 2  round-trip body console->PC->console: %d exact, %d differ  (%d pure materials)"
          % (rt_ok, rt_bad, rt_pure))


if __name__ == '__main__':
    main()
