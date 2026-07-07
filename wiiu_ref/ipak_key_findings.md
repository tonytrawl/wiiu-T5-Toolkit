# IPAK cross-platform key findings (2026-07-05, SOLVE session)

Task: section 0w reported 0% nameHash overlap between Wii U and PC ipaks, contradicting the
0u claim that the image name key carries across platforms. Resolve the key structure and
deliver a working PC source-blob lookup.

VERDICT: **0u was right, 0w's 0% was a parse bug in ipak.py, now fixed.** The name key does
carry over unchanged. Additionally the PC payload format (full .iwi files) is decoded and the
whole PC->Wii U texture path is proven pixel-identical on mp_raid.

## 1. Root cause of the 0% overlap: index key word order flips with file endianness

The 16-byte index entry is `{ u64 combinedKey, u32 offset, u32 size }` with
`combinedKey = nameHash << 32 | dataHash`, serialized in FILE endianness (it is one u64, per
the OAT `IPakIndexEntryKey` union). Consequence:

- big-endian paks (Wii U/360/PS3, magic `IPAK`): stored word order = nameHash, dataHash.
- little-endian paks (PC, magic `KAPI`): stored word order = **dataHash, nameHash**.

`ipak.py` read the first word as name_hash unconditionally, so on PC paks every "name_hash"
was actually the dataHash (a masked crc32, < 0x20000000, sorted ascending because the index
sorts by combinedKey; that is the "low-bit index-like pattern" 0w saw) and every membership
test compared Wii U name hashes against PC crc values: guaranteed 0 overlap. `white` etc.
matched nothing because those images are not streamed (no ipak entry), not because the hash
was wrong. Proof of the fix polarity: the index is sorted by combinedKey only under the
swapped interpretation (verified on base.ipak), and PC re-emit stays byte-exact after the fix.

ipak.py is corrected in both directions (read swaps on LE; write_ipak/reserialize emit the
swapped order for LE). Full harness still green, including the Wii U byte-exact GOLD rebuild.

## 2. Per-platform key, established from each platform's own zone + own ipak

Key scheme is IDENTICAL on both platforms:
`(nameHash, dataHash) = (R_HashString(imageName), partIndex<<29 | crc32(partPayload) & 0x1FFFFFFF)`
where nameHash == the GfxImage.hash field of that platform's .ff.

- Wii U (already proven earlier): all 124 mp_raid.ipak keys == (GfxImage.hash,
  streamedParts[i].hash) pairs of mp_raid_genuine.zone; payload crc == dataHash 124/124.
- PC (new): scanned `PC ff/mp_raid.zone` for GfxImage bodies (LE 80-byte struct; records kept
  only when stored hash == r_hash_string(name): 1096 images, 1094 streamed).
  **1094/1094 streamed images' (GfxImage.hash, streamedParts[0].hash) keys are present in
  PC base.ipak/mp.ipak**, and every extracted payload crc-verifies against its dataHash
  (LZO cmd 1). PC has one streamed part per image (streamedParts[1]), partIndex 0.
  Note: the PC .ff part's offset/size fields do NOT mirror the index entry offset/size
  (0/1094); lookup is by key, those fields are runtime/stale values.

## 3. PC<->Wii U relationship (the porting rule)

- nameHash: identical across platforms (pure function of the name). After the fix:
  **76/76** Wii U mp_raid.ipak nameHashes are found in PC base.ipak+mp.ipak.
- dataHash: platform-specific by design (crc of the platform-format payload); never expect
  overlap. On Wii U, partIndex (top 3 bits) is the console part ordinal; PC is always part 0.
- Payload format differs:
  - PC entry payload = a complete **.iwi file**: `IWi` magic, version 0x1B, u8 iwiFormat
    (0x0b DXT1, 0x0c DXT3, 0x0d DXT5, 0x0e DXT5-nm/BC5, 0x01/0x08 RGBA8), u8 flags,
    u16 width/height/depth, then mip data stored smallest-first with the TOP mip at the
    file tail (linear DDS block order).
  - Wii U entry payload = ONE GX2-tiled mip surface, no header.
- PIXEL IDENTITY PROVEN: for all **124/124** Wii U mp_raid.ipak entries,
  `gx2_texture.detile(wiiUPayload)` == the byte range of the corresponding mip inside the
  PC IWI blob for the same image. So the forward transcode is exactly:
  `iwi_mip_slice -> gx2_texture.tile() -> ipak.data_hash(payload, partIndex)` with no pixel
  conversion, no byte swap.

## 4. Deliverable: find_pc_source (in wiiu_ref/ipak.py)

- `parse_iwi(blob)` -> version/format (iwi + GX2 enum)/dims + per-mip (w, h, offset, size)
  table (top-down, offsets into the blob).
- `PcImageSource([pc ipak paths]).find_pc_source(name_or_pc_hash)` -> list of parts (PC:
  one), each `{name_hash, data_hash, part_index, blob, iwi}`; accepts the image name or the
  GfxImage.hash taken from any platform's .ff (they are equal).
- Proven in the harness (`python wiiu_ref/ipak.py`, all asserts green):
  - PC base.ipak (13366 entries) and mp.ipak (3298) re-emit byte-exact.
  - 76/76 Wii U mp_raid nameHashes resolve via find_pc_source.
  - 124/124 Wii U payloads byte-equal the GX2-detiled PC IWI mip slice.

## 5. Consequences for the port pipeline (supersedes the 0w gap)

For each streamed image of a ported map: take the name (or hash) from the PC .ff, pull the
IWI from the PC paks via find_pc_source, choose the console part grouping (mip ordinals per
0u/0f packed word), `tile()` each part's mip slice, `data_hash()` it, stamp .ff
streamedParts + write the map .ipak with `write_ipak()`. Images whose (nameHash, any-part
dataHash) already exist in the retail Wii U content set can be passthrough-referenced with
no work. The PC-source input gap of 0u/0w is closed.
