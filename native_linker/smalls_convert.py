#!/usr/bin/env python3
"""
PC(LE) -> console(BE) converters for the remaining small asset types of the
no-backbone assemble loop (Track G): SndBank (byte-copy), XAnimParts,
DestructibleDef, PhysPreset (standalone), GfxLightDef, Glasses, SkinnedVertsDef.

All layouts are PC-identical (probes: xanimparts_probe, destructibledef_probe;
T6_Assets.h structs) — conversion is per-field byte-swap + pointer reloc, with
strings/byte-arrays copied verbatim. Each convert_* returns (body_bytes, pc_end).
"""
import struct
import os
import material_convert as MC

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)


def _default_reloc(v):
    return v


class Sw:
    """LE->BE emit helper over a PC buffer with an advancing cursor."""
    def __init__(self, pc, o, reloc):
        self.pc = pc
        self.o = o
        self.b = bytearray()
        self.reloc = reloc

    def u16(self, n=1):
        for _ in range(n):
            self.b += struct.pack('>H', struct.unpack_from('<H', self.pc, self.o)[0])
            self.o += 2

    def u32(self, n=1):
        for _ in range(n):
            self.b += struct.pack('>I', struct.unpack_from('<I', self.pc, self.o)[0])
            self.o += 4

    def ptr(self, n=1):
        for _ in range(n):
            v = struct.unpack_from('<I', self.pc, self.o)[0]
            self.b += struct.pack('>I', self.reloc(v))
            self.o += 4

    def raw(self, n):
        self.b += self.pc[self.o:self.o + n]
        self.o += n

    def cstr(self):
        e = self.pc.index(b'\x00', self.o)
        self.b += self.pc[self.o:e + 1]
        self.o = e + 1

    def peek32(self, off):
        return struct.unpack_from('<I', self.pc, off)[0]


# ---------------------------------------------------------------- SndBank
# Optional overlay of the fixed SndBank head (4756 B) for the MAIN bank: the console
# SndAssetBankHeader carries .sab-file checksums (@body+0x830 = .sab header @0x38, engine
# Sys_Error's on mismatch -- hw-confirmed) plus the loadedAssets entryCount/dataSize that
# must match the DEPLOYED .sab. When the deployed .sab is genuine (raid control), overlay the
# genuine head; for converted .sab, this should instead be built from the console .sab headers.
SNDBANK_HEAD_OVERLAY = None
# .sab checksum / SndAssetBankHeader hash blocks (offset, length) in the fixed head, taken
# from genuine-vs-authored raid diff. @0x830 is the primary (.sab header @0x38).
SNDBANK_CKSUM_BLOCKS = [(0x830, 16), (0x940, 12), (0x1150, 20), (0x1264, 8)]

# Optional RAID oracle: supply the genuine console hash fields we CANNOT recompute (the
# console sound string-hash is custom/non-standard, and SndAlias.name is a per-build
# string-pool ptr-id). name@+0 & assetId@+16 are per-alias (positional: our emit order ==
# genuine alias order, proven by the BE re-walk); aliasIndex is the whole genuine array.
# Needed only where the DEPLOYED .sab uses genuine console hashes (raid oracle). For maps
# whose .sab we convert (skate etc.) the .sab id == our PC-derived assetId already, so leave
# these None. When set they overwrite our PC-derived values in-place (size-preserving).
SNDBANK_ALIAS_ORACLE = None       # list[(name_be:int, assetId_be:int)] in emit order
SNDBANK_ALIASINDEX_ORACLE = None  # bytes: genuine aliasIndex array (BE), len == aliasCount*4

# Whole-body overlay for the MAIN bank (raid control): dict {name: bytes}. The console bank
# inlines the list-name and assetFileName STRINGS (the paths the engine opens) plus its own
# custom-hash name/id fields; the PC bank stores those as hashes and omits the strings, so a
# field-aware convert leaves the alias region ~102KB short with the wrong FOLLOW-vs-hash layout
# -> a runtime sound-list pointer lands in the audio buffer -> +0x3817ce. Those strings/hashes
# are not derivable from PC (custom hash, strings absent). For a map WITH a genuine reference,
# emit the genuine main-bank body verbatim (self-contained FOLLOW+inline, loader relinks it).
# Keyed by the bank's walked name so it only replaces the intended bank.
SNDBANK_MAIN_OVERLAY = None       # {bank_name: genuine_body_bytes} or None
SNDBANK_LOADEDASSETS_ORACLE = None  # (entryCount, dataSize) genuine console values; overrides
                                    # console_zone_fields (which is off for raid: our dataSize was
                                    # 749KB too big -> shifted downstream GEN_POLICY bodies -> wild ptr)


def _swapw(b):
    """Byte-swap every 4-byte word (console v148 is big-endian). len(b) MUST be a
    multiple of 4 (all SndBank struct arrays are 4-aligned in size)."""
    return b''.join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


def _swap16(b):
    """Byte-swap every 2-byte half in place (u16/i16 fields)."""
    return b''.join(b[i:i + 2][::-1] for i in range(0, len(b), 2))


# --- field-aware SndAlias/SndRadverb/SndDuck endian (2026-07-12) ---------------
# The old blanket _swapw over these arrays was WRONG: it byte-reversed 4 bytes at a
# time across sub-u32 fields, corrupting (a) the SndAlias uint16/int16/uint8 tail
# (bytes 52..95) and its pad, and (b) the char name[32] of SndRadverb/SndDuck
# ("amb_"->"_bma"). Layouts from T6_Assets.h (SndAlias@6328, SndRadverb@3115,
# SndDuck@3139), byte-validated vs genuine raid mp_raid bank[1] (aligned aliases 0..3
# reproduce byte-exact except the two console-recomputed hash fields name@+0/assetId@+16
# and the per-alias flags1 bit26 'unknown1_1', neither of which is endian or a crash
# source). SndAliasList(20) and SndIndexEntry stay pure swap32.
def _alias_be(p100):
    """SndAlias(100) PC(LE)->console(BE), field-aware.
      +0..+51  : 6 ptr/u32 (name*,id,subtitle*,secondaryName*,assetId,assetFileName*)
                 + SndAliasFlags(8) + duck/contextType/contextValue/stopOnPlay/futzPatch -> swap32
      +52..+85 : 17 x u16/i16 (fluxTime..dopplerScale)                                  -> swap16
      +86..+95 : 10 x u8  (minPriorityThreshold..duckGroup)                             -> verbatim
      +96..+99 : pad                                                                    -> zero
    name@+0 & assetId@+16 carry the PC string-hash (console uses its own hash; wrong
    hash = sound not found by name = silent, NOT a wild-ptr crash) -- deferred."""
    return (_swapw(p100[0:52]) + _swap16(p100[52:86]) + p100[86:96]
            + b'\x00\x00\x00\x00')


def _radverb_be(p100):
    """SndRadverb(100): char name[32] verbatim + id + 16 floats -> swap32."""
    return p100[0:32] + _swapw(p100[32:100])


def _duck_be(p76):
    """SndDuck(76): char name[32] verbatim + (id,5 floats,2 u32,2 ptr,int) -> swap32."""
    return p76[0:32] + _swapw(p76[32:76])


def convert_sndbank(pc, off, reloc=_default_reloc):
    """PC(LE) SndBank -> console(BE): the layout is PC-IDENTICAL but the console
    is BIG-ENDIAN, so every struct WORD is byte-swapped while string bytes and the
    (zeroed) sample-data blob are kept verbatim (sndbank_probe: "console serializes
    PC-identically, byte-swap only"). The old verbatim copy left aliasCount/etc.
    little-endian -> the console read aliasCount as ~1.6e9 and walked the alias list
    off into unmapped memory (raid boot crash, 2026-07-12; the audio AXVPB frame
    callback). loadedAssets entries+data are a ZEROED RUNTIME BUFFER on console
    (FINDINGS_sndbank_loadedassets.md; audio lives in the .sabl/.sabs files). The walk
    mirrors sndbank_probe.parse_sndbank so word-regions and string-regions are emitted
    in stream order (arrays follow variable-length strings, so a blanket swap is wrong).
    NOTE: the SndAssetBankHeader hash blocks are byte-swapped structurally but their
    CONTENT is .sab-specific (genuine's hashes differ) -- bank-load hash validation is a
    separate transplant/recompute step, not the wild-pointer crash."""
    import sndbank_pc
    import sndbank_probe as _S
    import sndbank_audio_convert as SAC
    body = _S.BODY
    end, name, ac, stats = _S.parse_sndbank(pc, off, '<')
    nxt = sndbank_pc.parse_sndbank_pc(pc, off)
    # raid control: emit the genuine main-bank body verbatim (see SNDBANK_MAIN_OVERLAY).
    if SNDBANK_MAIN_OVERLAY is not None and name in SNDBANK_MAIN_OVERLAY:
        return SNDBANK_MAIN_OVERLAY[name], nxt
    u32 = lambda o: struct.unpack_from('<I', pc, o)[0]
    (name_p, aliasCount, alias_p, aliasIndex_p, radverbCount, radverbs_p,
     duckCount, ducks_p) = struct.unpack_from('<8I', pc, off)

    out = bytearray()
    out += _swapw(pc[off:off + body])           # fixed head (counts, bank headers)
    o = off + body

    def emit_string():                          # NUL-terminated string, verbatim
        nonlocal o
        nul = pc.index(b'\x00', o)
        out.extend(pc[o:nul + 1]); o = nul + 1

    alias_i = 0                                 # global alias index (for the oracle)
    if name_p in PTRS:
        emit_string()
    if alias_p in PTRS:
        arr_s = o; o += aliasCount * _S.ALIASLIST
        out += _swapw(pc[arr_s:o])              # SndAliasList[] array
        for i in range(aliasCount):
            lname_p, lid, head_p, cnt, seq = struct.unpack_from(
                '<5I', pc, arr_s + i * _S.ALIASLIST)
            if lname_p in PTRS:
                emit_string()                   # list name
            if head_p in PTRS:
                ab = o; o += cnt * _S.ALIAS
                for k in range(cnt):                # SndAlias[] array (field-aware)
                    a = ab + k * _S.ALIAS
                    ab_out = bytearray(_alias_be(pc[a:a + _S.ALIAS]))
                    if SNDBANK_ALIAS_ORACLE is not None:   # genuine name/assetId hashes
                        nm_be, aid_be = SNDBANK_ALIAS_ORACLE[alias_i]
                        # keep FOLLOW name fields (their inline string still follows -> the
                        # walk must still consume it); only replace the hash-name case.
                        if struct.unpack_from('>I', ab_out, 0)[0] not in PTRS:
                            struct.pack_into('>I', ab_out, 0, nm_be)
                        struct.pack_into('>I', ab_out, 16, aid_be)  # assetId never FOLLOW
                    out += ab_out
                    alias_i += 1
                for k in range(cnt):
                    a = ab + k * _S.ALIAS
                    for po in (a + 0, a + 8, a + 12, a + 20):   # name/sub/sec/file
                        if u32(po) in PTRS:
                            emit_string()
    if aliasIndex_p in PTRS:                       # SndIndexEntry{u16 value,u16 next}
        s = o; o += aliasCount * 4
        if SNDBANK_ALIASINDEX_ORACLE is not None:  # genuine console-rebuilt hash table
            out += SNDBANK_ALIASINDEX_ORACLE
        else:
            out += _swap16(pc[s:o])
        # NOTE: values are a name-hash open-addressing table the console REBUILDS from
        # its own string hashes (genuine != any transform of PC); swap16 fixes the field
        # endian only. It's a play-time name->alias lookup, not the boot bank walk, so a
        # PC-derived table is a silent miss at worst, not the +0x3817ce wild-ptr crash.
    if radverbs_p in PTRS:
        rs = o; o += radverbCount * _S.RADVERB    # SndRadverb[] (name[32] verbatim)
        for i in range(radverbCount):
            r = rs + i * _S.RADVERB
            out += _radverb_be(pc[r:r + _S.RADVERB])
    if ducks_p in PTRS:
        ds_s = o; o += duckCount * _S.DUCK        # SndDuck[] (name[32] verbatim)
        for i in range(duckCount):
            d = ds_s + i * _S.DUCK
            out += _duck_be(pc[d:d + _S.DUCK])
        for i in range(duckCount):
            db = ds_s + i * _S.DUCK
            for po in (db + 64, db + 68):        # attenuation/filter -> 32 f32
                if u32(po) in PTRS:
                    s = o; o += 32 * 4; out += _swapw(pc[s:o])
    # zone/language strings for each FOLLOW pointer in body[32..0x126c)
    for po in range(32, 0x126c, 4):
        if u32(off + po) == FOLLOW:
            emit_string()

    ec = u32(off + 0x1270)
    ds = u32(off + 0x1278)
    cec, cds = SAC.console_zone_fields(ec, ds)
    if SNDBANK_LOADEDASSETS_ORACLE is not None:     # genuine console entryCount/dataSize
        cec, cds = SNDBANK_LOADEDASSETS_ORACLE
    if u32(off + 0x1274) == FOLLOW:              # entries: zeroed capacity
        o += ec * 20; out += b'\x00' * (cec * 20)
    if u32(off + 0x127c) == FOLLOW:              # data: zeroed runtime buffer
        o += ds; out += b'\x00' * cds
    silc = u32(off + 0x1280)
    if u32(off + 0x1284) == FOLLOW:
        s = o; o += silc * 8; out += _swapw(pc[s:o])   # scriptIdLookups
    assert o == end, (hex(o), hex(end))
    # loadedAssets counts: BIG-ENDIAN, console-sized
    struct.pack_into('>I', out, 0x1270, cec)
    struct.pack_into('>I', out, 0x1278, cds)
    # main bank: overlay the deployed .sab's checksum/hash blocks (the SndAssetBankHeader hashes;
    # @0x830 = .sab header @0x38 -- engine Sys_Error's on mismatch). ONLY these blocks, NOT the
    # loadedAssets counts (those stay ours so the walk sizing remains self-consistent).
    if (SNDBANK_HEAD_OVERLAY is not None
            and u32(off + 0x1274) == FOLLOW and u32(off + 0x127c) == FOLLOW):
        for co, cl in SNDBANK_CKSUM_BLOCKS:
            out[co:co + cl] = SNDBANK_HEAD_OVERLAY[co:co + cl]
    return bytes(out), nxt


def author_english_bank(map_name,
                        template_zone=os.path.join('..', 'wiiu_ref',
                                                   'mp_raid_genuine.zone'),
                        template_off=0x45bea9e):
    """Author the console-only localized SndBank insert `mpl_<map>.english`
    (the extra SOUND row of the MP insert set, HANDOFF item).

    When the template zone's english bank IS this map's (raid control: the
    genuine mp_raid english bank), return its FULL genuine span VERBATIM
    (body + the 2 real VO aliases + name/zone strings). The aliases are the
    localized VO the engine registers and the AX voice callback walks — an
    EMPTIED bank leaves those dangling and faults at +0x3817ce (the audio
    callback; genuine-english bisect proved the full bank clears it, 2026-07-12,
    HANDOFF_xmodel_inline_image.md). The span is self-contained (all pointers
    FOLLOW with their inline alias/string data), so the loader relinks it in place.

    Cross-map (e.g. skate with the raid template): fall back to the genuine
    header/body with the alias/radverb/duck tables EMPTIED and strings
    re-authored — structurally valid and without cross-map VO alias refs (raid's
    VO streams a different map doesn't ship). That fallback is a stopgap; a real
    per-map english bank still needs its own localized VO."""
    import sndbank_probe as _S
    tz = template_zone if os.path.isabs(template_zone) else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), template_zone)
    d = open(tz, 'rb').read()
    end, tname, _ac, _st = _S.parse_sndbank(d, template_off, '>')
    base = 'mpl_%s' % map_name.replace('mp_', '', 1)
    # the template's own english bank matches this map -> ship it whole (aliases intact)
    if tname == '%s.english' % base:
        return bytes(d[template_off:end])
    # cross-map fallback: genuine header/body, alias tables emptied, strings re-authored
    body = bytearray(d[template_off:template_off + 4756])
    struct.pack_into('>I', body, 0, FOLLOW)      # name*
    for o in (4, 8, 12, 16, 20, 24, 28):         # aliasCount/alias/aliasIndex/
        struct.pack_into('>I', body, o, 0)       # radverbCount/radverbs/ducks*
    return bytes(body) + ('%s.english\x00%s\x00english\x00'
                          % (base, base)).encode('latin-1')


# ---------------------------------------------------------------- XAnimParts
def _conv_delta(s, numframes, idxw):
    pc = s.pc
    db = s.o
    ptrs = struct.unpack_from('<3I', pc, db)
    s.ptr(3)                                   # trans/quat2/quat ptrs
    if ptrs[0] in PTRS:                        # XAnimPartTrans
        size = struct.unpack_from('<H', pc, s.o)[0]
        small = pc[s.o + 2]
        if size == 0:
            s.u16(); s.raw(2); s.u32(3)        # u16+u8 small+pad, vec3 frame0
        else:
            frames_p = s.peek32(s.o + 28)
            s.u16(); s.raw(2); s.u32(6)        # hdr + mins/size vec3s
            s.ptr()                            # frames*
            if idxw == 1:
                s.raw(size + 1)
            else:
                s.u16(size + 1)
            if frames_p in PTRS:
                if small:
                    s.raw((size + 1) * 3)      # ByteVec
                else:
                    s.u16((size + 1) * 3)      # UShortVec
    for qsz in (4, 8):                         # quat2 (XQuat2=2xi16), quat (XQuat=4xi16)
        p = ptrs[1] if qsz == 4 else ptrs[2]
        if p not in PTRS:
            continue
        size = struct.unpack_from('<H', pc, s.o)[0]
        if size == 0:
            s.u16(); s.raw(2); s.u16(qsz // 2)  # u16+pad, inline frame0 quat
        else:
            frames_p = s.peek32(s.o + 4)
            s.u16(); s.raw(2)
            s.ptr()                            # frames*
            if idxw == 1:
                s.raw(size + 1)
            else:
                s.u16(size + 1)
            if frames_p in PTRS:
                s.u16((size + 1) * (qsz // 2))


def convert_xanim(pc, off, reloc=_default_reloc):
    """XAnimParts: PC-identical 104-B body + streamed data, per-field swap."""
    s = Sw(pc, off, reloc)
    (dbc, dsc, dic, rdbc, rdic, numframes) = struct.unpack_from('<6H', pc, off + 4)
    boneCount = pc[off + 24:off + 34]
    notifyCount = pc[off + 34]
    rdsc = s.peek32(off + 40)
    indexCount = s.peek32(off + 44)
    idxw = 1 if numframes < 256 else 2
    p = lambda o: s.peek32(off + o)
    # ---- 104-B body ----
    s.ptr()                                    # name
    s.u16(6)                                   # counts @4..15
    s.raw(4)                                   # bLoop..bLeftHandGripIK u8s @16
    s.u32()                                    # streamedFileSize @20
    s.raw(12)                                  # boneCount[10] + notifyCount + assetType @24..35
    s.raw(4)                                   # isDefault + pad @36
    s.u32(2)                                   # randomDataShortCount, indexCount @40,44
    s.u32(4)                                   # framerate/frequency/primedLength/loopEntryTime @48
    s.ptr(10)                                  # names..deltaPart @64..100
    assert s.o == off + 104
    # ---- dynamic stream (probe order) ----
    if p(0) == FOLLOW:
        s.cstr()                               # name string
    if p(64) in PTRS:
        s.u16(boneCount[9])                    # names: scriptstring u16s
    if p(96) in PTRS:
        for _ in range(notifyCount):           # notify: u16 name + pad2 + f32 time
            s.u16(); s.raw(2); s.u32()
    if p(100) in PTRS:
        _conv_delta(s, numframes, idxw)
    if p(68) in PTRS:
        s.raw(dbc)                             # dataByte
    if p(72) in PTRS:
        s.u16(dsc)                             # dataShort
    if p(76) in PTRS:
        s.u32(dic)                             # dataInt
    if p(80) in PTRS:
        s.u16(rdsc)                            # randomDataShort
    if p(84) in PTRS:
        s.raw(rdbc)                            # randomDataByte
    if p(88) in PTRS:
        s.u32(rdic)                            # randomDataInt
    if p(92) in PTRS:                          # indices
        if idxw == 1:
            s.raw(indexCount)
        else:
            s.u16(indexCount)
    return bytes(s.b), s.o


# ---------------------------------------------------------------- DestructibleDef
def _conv_physconstraints(s):
    """PhysConstraints 2696: name + count + 16 x PhysConstraint(168)."""
    cb0 = s.o
    s.ptr()                                    # name
    s.u32()                                    # count
    for c in range(16):
        s.u16(); s.raw(2)                      # targetname + pad
        s.u32(2)                               # type, attach_point_type1
        s.u32()                                # target_index1
        s.u16(); s.raw(2)                      # target_ent1 + pad
        s.ptr()                                # target_bone1
        s.u32(2)                               # attach_point_type2, target_index2
        s.u16(); s.raw(2)                      # target_ent2 + pad
        s.ptr()                                # target_bone2
        s.u32(25)                              # offset..maxAngle @40..139
        s.ptr()                                # material @140
        s.u32(6)                               # constraintHandle/rope_index/centity_num[4]
    assert s.o == cb0 + 2696
    # dynamic: name string + per-constraint bone strings
    if s.peek32(cb0) in PTRS:
        s.cstr()
    for c in range(16):
        cb = cb0 + 8 + c * 168
        if s.peek32(cb + 20) in PTRS:
            s.cstr()
        if s.peek32(cb + 36) in PTRS:
            s.cstr()


def convert_destructible(pc, off, reloc=_default_reloc):
    """DestructibleDef: PC-identical (destructibledef_probe), 24-B body +
    numPieces x 312-B pieces + per-piece strings/physConstraints."""
    s = Sw(pc, off, reloc)
    num = s.peek32(off + 12)
    s.ptr(3)                                   # name/model/pristineModel
    s.u32()                                    # numPieces
    s.ptr()                                    # pieces
    s.u32()                                    # clientOnly
    if s.peek32(off) in PTRS:
        s.cstr()                               # name
    if s.peek32(off + 16) in PTRS:
        base = s.o
        for i in range(num):                   # 312-B piece bodies
            for st in range(5):                # 5 stages x 48
                s.u16(); s.raw(2)              # showBone + pad
                s.u32(3)                       # breakHealth/maxTime/flags
                s.ptr(8)                       # breakEffect..physPreset @16..47
            s.raw(4)                           # parentPiece + pad @240
            s.u32(6)                           # damage scales @244..267
            s.ptr()                            # physConstraints @268
            s.u32()                            # health @272
            s.ptr(3)                           # damageSound/burnEffect/burnSound
            s.u16(); s.raw(2)                  # enableLabel + pad @288
            s.u32(5)                           # hideBones[5]
        assert s.o == base + num * 312
        for i in range(num):                   # per-piece dynamics, probe order
            pb = base + i * 312
            for st in range(5):
                sb = pb + st * 48
                for so in (sb + 20, sb + 24, sb + 28):
                    if s.peek32(so) in PTRS:
                        s.cstr()
            if s.peek32(pb + 268) in PTRS:
                _conv_physconstraints(s)
            if s.peek32(pb + 276) in PTRS:
                s.cstr()
            if s.peek32(pb + 284) in PTRS:
                s.cstr()
    return bytes(s.b), s.o


# ---------------------------------------------------------------- PhysPreset
def convert_physpreset(pc, off, reloc=_default_reloc):
    """Standalone PhysPreset asset: 84-B all-4-byte body + name/sndAliasPrefix."""
    s = Sw(pc, off, reloc)
    s.ptr()                                    # name
    s.u32(6)                                   # flags..explosiveForceScale
    s.ptr()                                    # sndAliasPrefix @28
    s.u32(13)                                  # piecesSpreadFraction..buoyancyBoxMax
    assert s.o == off + 84
    if s.peek32(off) in PTRS:
        s.cstr()
    if s.peek32(off + 28) in PTRS:
        s.cstr()
    return bytes(s.b), s.o


# ---------------------------------------------------------------- GfxLightDef
def convert_lightdef(pc, off, reloc=_default_reloc):
    """GfxLightDef: 16-B body + name + inline GfxImage cookie (image converter)."""
    s = Sw(pc, off, reloc)
    s.ptr(3)                                   # name / attenuation.image / samplerState
    s.u32()                                    # lmapLookupStart
    if s.peek32(off) in PTRS:
        s.cstr()
    if s.peek32(off + 4) in PTRS:
        body, nxt = MC.convert_image(pc, s.o, reloc)
        s.b += body
        s.o = nxt
    return bytes(s.b), s.o


# ---------------------------------------------------------------- Glasses
def convert_glasses(pc, off, reloc=_default_reloc):
    """Glasses: 56-B body + name + numGlasses x Glass(140) + per-glass
    inline GlassDef(60)/materials/FX/outline verts."""
    import fx_convert as FXC
    s = Sw(pc, off, reloc)
    num = s.peek32(off + 4)
    s.ptr()                                    # name
    s.u32()                                    # numGlasses
    s.ptr()                                    # glasses
    s.u32((56 - 12) // 4)                      # remainder of 56-B body (4-byte scalars)
    if s.peek32(off) in PTRS:
        s.cstr()
    if s.peek32(off + 8) in PTRS:
        gbase = s.o
        for i in range(num):                   # Glass 140-B bodies
            s.u32()                            # numCellIndices
            s.u16(6)                           # cellIndices[6]
            s.ptr()                            # glassDef @16
            s.u32(2)                           # index/brushModel
            s.u32(12)                          # origin/angles/absmin/absmax
            s.raw(4)                           # isPlanar/numOutlineVerts/binormalSign/pad
            s.ptr()                            # outline @80
            s.u32(14)                          # outlineAxis[3]+outlineOrigin+uvScale+thickness
        assert s.o == gbase + num * 140
        for i in range(num):
            gb = gbase + i * 140
            if s.peek32(gb + 16) in PTRS:      # inline GlassDef
                gd = s.o
                s.ptr()                        # name
                s.u32(6)                       # maxHealth..maxShards
                s.ptr(3)                       # pristine/cracked/shard Material
                s.ptr(3)                       # crackSound/shatterShound/autoShatterShound
                s.ptr(2)                       # crack/shatterEffect
                if s.peek32(gd) in PTRS:
                    s.cstr()
                for mo in (28, 32, 36):
                    if s.peek32(gd + mo) in PTRS:
                        body, nxt = MC.convert_material(pc, s.o, reloc)
                        s.b += body
                        s.o = nxt
                for so in (40, 44, 48):
                    if s.peek32(gd + so) in PTRS:
                        s.cstr()
                for fo in (52, 56):
                    if s.peek32(gd + fo) in PTRS:
                        body, nxt, _ = FXC.convert_fx(pc, s.o, reloc)
                        s.b += body
                        s.o = nxt
            if s.peek32(gb + 80) in PTRS:      # outline verts
                s.u32(pc[gb + 77] * 2)         # numOutlineVerts x vec2
    return bytes(s.b), s.o


# ---------------------------------------------------------------- GameWorldMp
def _gwmp_pathnode(s):
    """pathnode_t 144: constant(68) + dynamic(48) + transient(28). Returns the
    Links pointer value. Field widths = the chase probe's executable spec
    (probe_gameworldmp_convert.py, byte-exact on raid + dockside)."""
    s.u32(2)                                   # type, spawnflags
    s.u16(5)                                   # targetname..animscript scriptstrings
    s.raw(2)                                   # pad
    s.u32()                                    # animscriptfunc
    s.u32(8)                                   # vOrigin[3] fAngle forward[2] fRadius minUseDistSq
    s.u16(3)                                   # wOverlapNode[2] totalLinkCount
    s.raw(2)                                   # pad
    links = s.peek32(s.o)
    s.ptr()                                    # Links
    s.u16(2)                                   # SentientHandle
    s.u32(8)                                   # iFreeTime iValidTime[3] danger[3] LOS
    s.u16(4)                                   # wLinkCount wOverlapCount turret userCount
    s.raw(4)                                   # bool + pad
    s.u32(7)                                   # transient
    return links


def _gwmp_tree_node(s):
    axis = struct.unpack_from('<i', s.pc, s.o)[0]
    s.u32(2)                                   # axis, dist
    if axis < 0:
        cnt = s.peek32(s.o)
        s.u32()                                # u.s.nodeCount
        p = s.peek32(s.o)
        s.ptr()                                # u.s.nodes
        return ('leaf', cnt, p)
    a = s.peek32(s.o); s.ptr()
    b = s.peek32(s.o); s.ptr()
    return ('split', a, b)


def _gwmp_tree_dyn(s, info):
    if info[0] == 'leaf':
        _, cnt, p = info
        if p in PTRS:
            s.u16(cnt)
    else:
        for child in info[1:]:
            if child in PTRS:
                _gwmp_tree_dyn(s, _gwmp_tree_node(s))


def convert_gameworldmp(pc, off, reloc=_default_reloc):
    """GameWorldMp: PC/console serialization IDENTICAL (chase findings §2).
    44-B body + (nodeCount+128) x pathnode_t(144) + per-node pathlink_s(16)
    + pathVis/smoothCache raw + nodeTree. basenodes are RUNTIME (0 bytes)."""
    s = Sw(pc, off, reloc)
    nodeCount = s.peek32(off + 4)
    nodes_p = s.peek32(off + 12)
    visBytes = s.peek32(off + 20)
    vis_p = s.peek32(off + 24)
    smoothBytes = s.peek32(off + 28)
    smooth_p = s.peek32(off + 32)
    treeCount = s.peek32(off + 36)
    tree_p = s.peek32(off + 40)
    s.ptr()                                    # name
    s.u32(2)                                   # nodeCount, originalNodeCount
    s.ptr(2)                                   # nodes, basenodes(runtime)
    s.u32()                                    # visBytes
    s.ptr()                                    # pathVis
    s.u32()                                    # smoothBytes
    s.ptr()                                    # smoothCache
    s.u32()                                    # nodeTreeCount
    s.ptr()                                    # nodeTree
    if nodes_p in PTRS:
        per_node = [_gwmp_pathnode(s) for _ in range(nodeCount + 128)]
        tots = [struct.unpack_from('<H', pc, off + 44 + i * 144 + 60)[0]
                for i in range(nodeCount + 128)]
        for tot, links in zip(tots, per_node):
            if links in PTRS:
                for _ in range(tot):
                    s.u32()                    # fDist
                    s.u16()                    # nodeNum
                    s.raw(10)                  # u8 fields + pad (16-B stride)
    if vis_p in PTRS:
        s.raw(visBytes)
    if smooth_p in PTRS:
        s.raw(smoothBytes)
    if tree_p in PTRS:
        infos = [_gwmp_tree_node(s) for _ in range(treeCount)]
        for inf in infos:
            _gwmp_tree_dyn(s, inf)
    return bytes(s.b), s.o


# ---------------------------------------------------------------- ScriptParseTree
def convert_scriptparsetree(pc, off, reloc=_default_reloc):
    """ScriptParseTree via the validated GSC transcoder (gsc_swap: 13/13 raid +
    17/17 dockside byte-exact). Body pointers are always FOLLOW (gsc_swap
    asserts), so no reloc is needed. Span: 12-B struct + name + buffer + NUL."""
    import gsc_swap
    ln = struct.unpack_from('<I', pc, off + 4)[0]
    end = pc.index(b'\x00', off + 12) + 1 + ln + 1
    return gsc_swap.convert_spt_body(pc[off:end]), end


# ---------------------------------------------------------------- SkinnedVertsDef
def convert_skinnedverts(pc, off, reloc=_default_reloc):
    """SkinnedVertsDef: console body is 24 B — {name*, maxSkinnedVerts} plus 4
    extra FOLLOW pointer words PC lacks (runtime vert buffers) — then the name
    string and a trailing u32=0 (verified against genuine raid: 41 B total)."""
    s = Sw(pc, off, reloc)
    s.ptr()
    s.u32()
    s.b += b'\xff' * 16
    if s.peek32(off) in PTRS:
        s.cstr()
    s.b += b'\x00\x00\x00\x00'
    return bytes(s.b), s.o
