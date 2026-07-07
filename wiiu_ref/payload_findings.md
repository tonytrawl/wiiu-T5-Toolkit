# Payload authoring findings: IPAK container + GSC injection (2026-07-04, payload session)

Deliverables: `wiiu_ref/ipak.py` (IPAK read/write), `wiiu_ref/gsc_inject.py` (SPT payload swap).
Both are pure Python, self-verifying (`python wiiu_ref/ipak.py`, `python wiiu_ref/gsc_inject.py --selftest`).
No OAT builds, no edits to tools/ref_oat or WIIU_UNLINK_STATUS.md.

HEADLINE: genuine Wii U ipaks were provided mid-session
(`C:\Users\Tony - Main Rig\Downloads\Wii U Call of Duty Black Ops 2 USA WUP\wuo\content\*.ipak`).
`write_ipak()` rebuilds the retail `content/mp_raid.ipak` (23,330,816 bytes, 124 entries) BYTE-EXACT
from nothing but its (nameHash, dataHash, payload) triples, so the writer is retail-canonical, not
just format-plausible. All 2249 streamed part keys referenced by mp_raid_genuine.zone resolve across
the retail paks (see section 5).

## 1. T6 IPAK container format (SOLVED, byte-exact, retail-Wii-U-canonical)

Derived from genuine Wii U `content/mp_raid.ipak` + `content/common_mp.ipak` + splits,
`xbox_nuketown_extracted/zm_nuked.ipak` (1603 entries), `xbox_nuketown_extracted/dlczm0_load_zm.ipak`
(4 entries), `ps3 ff/zm_nuked.ipak` (3044 entries), cross-checked against the OAT reference code
(`tools/ref_oat/src/ObjCommon/ObjContainer/IPak/*`, `ObjCompiling/Image/IPak/IPakCreator.cpp`,
read-only). The container is identical across platforms; endianness, compression codec, and the Wii U
metadata sections differ.

- Header 16 B: magic `IPAK` (BE file: Wii U/360/PS3, CONFIRMED on retail Wii U) or `KAPI` (LE: PC),
  u32 version 0x50000, u32 fileSize, u32 sectionCount.
- Sections, 16 B each, directly after the header: `{ u32 type, u32 offset, u32 size, u32 itemCount }`.
  type 1 = index, type 2 = data. 360/PS3 retail paks have exactly these two. Wii U retail paks add
  type 4 (8 B per item: the {nameHash, dataHash} key of every part the MAP uses, including parts that
  live in other paks; mp_raid: 2361 items vs 124 stored entries) and type 3 (variable-length records
  `{nameHash, dataHash, u32 seq, u32 0, "iwi: images/<name>.iwi\nformat: DXT5\noffset: ...\n..."}`).
  Both are linker metadata; `ipak.py` carries them opaquely and they are not needed to author a
  working pak (the engine reader per OAT touches only sections 1 and 2). OAT-authored paks add a
  `META` branding section instead.
- Index entry 16 B: `{ u32 nameHash, u32 dataHash, u32 offset, u32 size }` where the two hash words are
  the BE serialization of `u64 combinedKey = nameHash<<32 | dataHash`. Entries sorted by combinedKey.
  `offset` is relative to the data section start; `size` is the FILE span of the entry
  (block headers + payloads). Entries are contiguous: offsets tile the data section exactly
  (holds on Wii U, 360, and PS3 paks).
- Data section: per entry a run of blocks. Block = 128 B header
  `{ u32 first = count<<24 | entryRelativeDecompressedOffset(24 bits); u32 commands[31] }`
  followed by the command payloads back to back. Command u32 = `compressed<<24 | size(24 bits)`.
  compressed: 0 = raw copy, 1 = LZO1X, 2 = XMemCompress/LZX (Xbox 360 only), 0xCF = skip (padding;
  its countAndOffset word is `1<<24 | 0`, not the running offset). Block headers are 128-aligned.
- Retail Wii U data layout (measured and byte-exactly reproduced):
  - payloads are UNCOMPRESSED (cmd 0), 0x7FF0 bytes per command (OAT writes 0x7F00 LZO).
  - read windows are 0x40000 wide anchored at the previous 0x8000 boundary of the entry's first
    block header. No block and no command spans a window boundary: the linker closes the block,
    emits a 1-command skip block padding to the boundary, then an 8 x 0x7FF0-command block fills
    each whole window. Only the entry's final command may be short.
  - pad bytes: 0xA7 between sections and at file end, 0x93 for 128-alignment inside the data
    section, 0xCD inside skip commands. Sections and file end are 0x40000-aligned.
- Platform compression observed: Wii U = uncompressed (cmd 0), PS3 = LZO1X (cmd 1),
  Xbox 360 = XMem/LZX (cmd 2), PC retail = LZO per OAT.
- Each Wii U entry payload is exactly ONE GX2-tiled mip-level surface: for all 124 mp_raid entries,
  payload size == `gx2_texture.surface_info(fmt, partW, partH, tileMode).size` with the format and
  part dims taken from the zone GfxImage (tileMode 4, degrading to 2 for small levels). Extracted
  blobs detile+decode to correct images (wood panel, patio heater etc. eyeballed from PNG).

## 2. Hash algorithm and .ff linkage (SOLVED)

- `nameHash = R_HashString(imageName)`: `h = (33*h) ^ (byte | 0x20)`, seed 0 (case-folding djb-xor,
  `tools/ref_oat/src/ObjLoading/ObjContainer/IPak/IPak.cpp`). Verified 8/8 against genuine stored hashes
  (360 dlczm0 names and Wii U mp_raid names).
- This is exactly the u32 the GfxImage asset stores as its `hash` field (console +324 per status doc 0f,
  PC at body+76). So the .ff image ref and the ipak index key derive from the same function.
- `dataHash = (partIndex << 29) | (crc32(decompressedPartPayload) & 0x1FFFFFFF)`.
  Verified crc-exact on 3044/3044 genuine PS3 entries (full LZO decode + crc sweep) AND on all
  124 genuine Wii U mp_raid.ipak entries (uncompressed payloads).
  The console GfxImage `streamedParts[i]` hash word at part+4 holds exactly this value:
  the 4 keys of dlczm0_load_zm.ipak were found verbatim in dlczm0_load_zm.zone at
  streamedParts+4 (dataHash) and GfxImage.hash (nameHash); on Wii U all 124 mp_raid.ipak keys
  match (GfxImage.hash, streamedParts[i].hash) pairs from mp_raid_genuine.zone exactly; part
  index in the top 3 bits matches part position across the whole Wii U mp_raid corpus
  (1018 streamed images). partIndex 0 = the low-mip part.
- The packed word at part+0 ({levelCount:4, levelSize:28} per PC header) is NOT the payload size:
  low nibble = mip ordinal of the part (observed 8..0xA), upper bits = cumulative resident size
  (this part's surface + all lower-mip surfaces, GX2-aligned; e.g. 512x512 BC3 part: payload
  0x40000, packed size 0x58000). Authoring it belongs to the .ff write path (WP-H); it is
  derivable from `gx2_texture.mip_chain()`.
- The 360 GfxImage tail mirrors the Wii U one: ...streamedParts[3] x 44 B, partCount, name ptr, hash;
  only the GPU header up front differs (Xenos vs GX2).

## 3. PC / Wii U hash parity (ANSWERED)

- nameHash parity: YES by construction (pure function of the name) and confirmed on data:
  PC mp_raid.zone stores byte-identical image hash values for the same image names as
  Wii U mp_raid_genuine.zone (10/10 sampled), and 438 of 444 nameHashes in the 360 zm_nuked ipak
  reappear verbatim in the PS3 zm_nuked ipak. **.ff image name refs carry over unchanged.**
- dataHash parity: NO, by design. It is a crc of the platform-tiled pixel payload:
  360 vs PS3 zm_nuked share 438 nameHashes but 0 (nameHash,dataHash) pairs.
  Consequence for porting: after GX2-tiling a texture part for Wii U, compute a fresh
  `dataHash(payload, partIndex)` and write the SAME value into both the ipak index and the
  GfxImage streamedParts entry of the .ff. They only have to agree with each other.
- Part scheme: PC GfxImage carries `streamedParts[1]` (one part) with its own level grouping;
  consoles carry up to 3 (PC bitfield allows ipakIndex 0..15; observed part indices 0..3 PS3, 0..4 360
  across paks). A PC->Wii U port must regroup mip levels into console parts; the grouping is visible in
  the packed level word at part+0 ({levelCount:4, levelSize:28} per status doc 0f).

## 4. wiiu_ref/ipak.py (delivered)

- Read: parses header/sections/index (plus Wii U metadata sections 3/4, carried opaquely),
  `extract(entry)` decodes cmd 0/1/0xCF (cmd 2 = XMem raises: pure-Python LZX not implemented;
  360 payloads are not needed for Wii U authoring), optional crc verification against dataHash.
  Includes a pure-Python LZO1X decompressor (transcribed from minilzo lzo1x_d.c).
- Write: `write_ipak([(name_or_hash, partIndex_or_dataHash, payload), ...], endian='>',
  extra_sections=..., keep_order=...)` authors a console pak with the exact retail Wii U layout
  (cmd 0, 0x7FF0 commands, window/skip/pad rules above), sorted index. `data_hash()` /
  `r_hash_string()` exported so the .ff writer can stamp matching streamedParts.
- Verification (all green, `python wiiu_ref/ipak.py`):
  - read -> re-emit -> byte-exact against genuine Wii U mp_raid.ipak, 360 zm_nuked/dlczm0, and
    PS3 zm_nuked (proves every header/index/layout field is parsed, nothing inferred).
  - GOLD: retail Wii U mp_raid.ipak rebuilt byte-exact by `write_ipak()` from its
    (key, payload) triples + carried metadata sections.
  - 3044/3044 PS3 entries LZO-decoded with crc32 dataHash match; 124/124 Wii U entries
    crc-verified; sample Wii U blobs detiled + decoded to correct PNGs via gx2_texture.py.
  - Authoring round trip: 12 genuine GX2-tiled payloads pulled from mp_raid_genuine.zone ->
    new BE ipak -> re-read -> byte-exact, all keys re-derived from name + payload only.

## 5. Retail pak population and the common-asset passthrough (MEASURED)

Resolving every streamed part key of mp_raid_genuine.zone (2249 keys = 1018 part0 + 793 part1
+ 438 part2) against `content/*.ipak`:

| pak | keys resolved |
|---|---|
| mp_raid.ipak | 124 (map-unique parts 1/2) |
| base_split1..5.ipak | 1107 (shared parts 1/2) |
| lowmip_split1..2.ipak | 1018 (ALL part0 low-mip parts) |
| total | 2249/2249, nothing unresolved |

So: part0 payloads never sit in the map pak (lowmip_split*), and a map pak carries only the
map-unique high-mip parts. The common-asset passthrough for a ported map is a pure key lookup:
any (nameHash, dataHash) already present in the retail content set can be referenced by the .ff
streamedParts as-is with NO pixel work and NO ipak entry of our own; only genuinely new textures
go into the new map .ipak (all three parts, including part0, since lowmip_split won't have it).
common.ipak is empty (0 entries) and common_mp.ipak's 183 entries serve common_mp.ff, not maps.

## 6. Still needs real files

- A PC .ipak (e.g. Steam mp_raid.ipak / common.ipak): source blobs for the PC->Wii U texture path.
  Pipeline once present: extract PC part by (nameHash, PC dataHash from the PC .ff), regroup mips
  to console parts, `gx2_texture.tile()` each part, `data_hash()` it, `write_ipak()` + stamp the
  .ff streamedParts (including the packed level word, see section 2).
- Note: `python tools/ff_decrypt.py` cannot open the PS3 .ff (different Salsa20 key) and the 360 .ff
  needs the OAT exe (LZX); neither blocked this work.

## 7. GSC injection: wiiu_ref/gsc_inject.py (delivered)

- `find_spt_buffers(zone)` locates every serialized SCRIPTPARSETREE (FOLLOW name ptr, u32 len,
  FOLLOW buffer ptr, .gsc/.csc path, 0x80 GSC magic; len read in the endianness that fits, so it works
  on BE console zones and LE PC zones alike).
- `inject(zone)` transcodes each buffer with `gsc_diff.pc_gsc_to_console()` IN PLACE. Safe because the
  SPT layout is PC-identical and the transcode is byte-length preserving. Endianness of each buffer is
  detected from GSCOBJ header-offset plausibility, so the tool is idempotent and skips
  already-console buffers (mixed zones fine).
- Verification (all green, `--selftest` plus common_mp/PC runs):
  - genuine Wii U zones pass through byte-identical (0 rewrites): mp_raid 13 SPTs, zm_transit 2,
    common_mp 30.
  - console->pc->console round trip byte-exact on all 45 genuine Wii U buffers.
  - synthetic ported zone (genuine Wii U zone with every buffer converted to PC endianness) ->
    `inject()` -> byte-exact equal to the genuine zone (mp_raid and zm_transit).
  - real PC zone (PC ff/mp_raid.zone): 13/13 buffers found and transcoded, none detects as LE after.

## 8. Corrections / notes for the master doc merge

- Status doc 0f calls streamedParts+4 "ipak hash": it is precisely
  `(partIndex<<29) | crc32(partPayload) & 0x1FFFFFFF`, the low u64 word of the ipak index key,
  and GfxImage.hash (+324) is the high word (R_HashString of the name).
- The scratch scan scripts (GfxImage tail-signature scanner, hash attacks) live in the session
  scratchpad, not in wiiu_ref; the durable logic is inside ipak.py's verify harness.
