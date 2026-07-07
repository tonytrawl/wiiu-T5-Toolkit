# Wii U (T6 v148) minor asset-type console layouts + GSC transcode findings

Combined SOLVE deliverable for Part A (WP-C minor types + GameWorldMp) and
Part B (GSC transcode, tasks #15/#18). Pure Python, no OAT build. Every
claim below is backed by an executable probe in this directory and a
genuine .bin sample. Verification zones: Wii U mp_raid_genuine.zone,
zm_transit_original.zone, common_mp.zone (root); PC oracles
PC ff/mp_raid.zone, PC ff/common_mp.zone, PC ff/zm_nuked.zone.

Headline: EVERY type in this batch is PC-IDENTICAL in layout (byte-swap
only). No dropped members, no inserted members, no console struct-size
change anywhere in SCRIPTPARSETREE, RAWFILE, KEYVALUEPAIRS,
FOOTSTEP_TABLE(S), GAMEWORLD_MP, DESTRUCTIBLEDEF, XANIMPARTS, or SndBank
(one open 4-byte question on common_mp's SndBank tail). Implementation in
OAT is therefore routing-only for all of them (like FX/clipMap): the
generated PC loader with SwapEndianness() already consumes the right
bytes.

## Part A summary table

| Type | Probe | Console layout | Verification |
|---|---|---|---|
| SCRIPTPARSETREE | scriptparsetree_probe.py | PC-identical. 12 B body {name* FOLLOW, i32 len, byte* buffer FOLLOW}; consumption 12 + name+1 + (len+1). The +1 (ZoneCode `count buffer len + 1`) is real: buffer[len]==0 and next SPT starts exactly there. | 13 assets mp_raid WU + 13 PC + 2 zm, 9/13 hard-chained, run ends land on next asset. Sample: console_scriptparsetree_sample.bin |
| RAWFILE | rawfile_probe.py | PC-identical. Same 12 B shape, `len + 1` rule identical. | 59 found zm (43 hard chains), mp_raid + PC vision files. Sample: console_rawfile_sample.bin |
| KEYVALUEPAIRS | keyvaluepairs_probe.py | PC-identical. 12 B body {name*, u32 numVariables, KeyValuePair*}; pairs = 12 B {keyHash, namespaceHash, value*}; array rule bodies-then-strings. | Asset[0] in both zones; walk lands exactly on asset[1] body. Sample: console_keyvaluepairs_sample.bin |
| FOOTSTEP_TABLE | footstep_table_probe.py | PC-identical. 900 B {name*, u32 sndAliasTable[32][7]}. NOTE: the 896 table bytes are BYTE-IDENTICAL PC vs Wii U (hash words not swapped in-file); copy verbatim on relink. Name may be an alias (later tables in the run). | 7-table mp_raid chain and 6-table zm chain hard-chain on WU; same 7 chain on PC. Sample: console_footsteptable_sample.bin |
| FOOTSTEPFX_TABLE | footstep_table_probe.py | PC-identical. 132 B {name*, FxEffectDef*[32]}; slots are null/alias only in genuine zones. | zm + PC instances resync to a FOLLOW body. |
| LEADERBOARD | (none possible) | NOT PRESENT in any genuine Wii U zone on hand (mp_raid, zm_transit, common_mp; PC copies likewise). Presume PC-identical (36 B + 44 B LbColumnDef, all scalars/strings, TEMP block, same family as every other type here). Verify when a zone containing one appears. | n/a |
| GAMEWORLD_MP | gameworldmp_probe.py | PC-identical. 44 B body {name* (alias to the d3dbsp string), PathData}; dynamics per GameWorldSp.txt rules: (nodeCount+128) x pathnode_t 144 B (constant 68 + dynamic 48 + transient 28, transient not followed), per node Links = totalLinkCount x pathlink_s 16 B, pathVis, smoothCache, nodeTree 16 B nodes with recursion. | Byte-exact WU mp_raid (lands on glass techset body 0x40f5989), WU zm (lands on next body 0x62c3a02), PC mp_raid (lands on PC techset body). Sample: console_gameworldmp_sample.bin |
| DESTRUCTIBLEDEF | destructibledef_probe.py | PC-identical. 24 B body; DestructiblePiece 312 B (5 x 48 B stages @0, parentPiece @240, scales @244, physConstraints @268, health @272, damageSound @276, burnEffect @280, burnSound @284, enableLabel u16 @288, hideBones[5] @292). Names are ALIASES (the identical string already exists in the StringTable csv asset). Dynamics: pieces bodies, then per piece the stage breakSound/breakNotify/loopSound and piece damageSound/burnSound strings. All asset refs alias. | 8/8 WU = 8/8 PC with identical per-asset byte counts; all resync. Sample: console_destructibledef_sample.bin |
| XANIMPARTS | xanimparts_probe.py | PC-identical. 104 B body; stream order name, names (boneCount[9] x u16), notify (8 B each), deltaPart, dataByte, dataShort, dataInt, randomDataShort, randomDataByte, randomDataInt, indices (u8 if numframes<256 else u16). Delta records per the probe docstring (frames arrays 4-aligned; trans frame data ByteVec 3 B / UShortVec 6 B). | 1183 WU zm bodies parsed, 1082 hard-chained; 1462 PC zm_nuked, 1207 chained; mp_raid pair consumption identical (1534 / 9801 B). All non-chaining ends are run ends or false anchors. Sample: console_xanimparts_sample.bin |
| SOUND / SndBank | sndbank_probe.py | PC-identical serialization. Body 4756 B (mp_raid, both platforms). Alias machinery: SndAliasList 20 B, SndAlias 100 B (4 string ptrs), SndIndexEntry 4 B, SndRadverb 100 B, SndDuck 76 B + 2x128 B curves; loadedAssets tail at fixed body offsets 0x1264..0x1284: entries 20 B each, then dataSize bytes of INLINE sample data (Wii U embeds 11.5 MB in mp_raid.all). Section-0d bitfield: SndAliasFlags is 8 bytes on both platforms; only bit order within the words is console-different, which does not affect stream walking. | WU mp_raid: both banks walked 12.9 MB byte-exact onto the XANIMPARTS body. WU common_mp common.all (23.9 MB) resyncs onto the next asset. Sample: console_sndbank_sample.bin |

Open items in Part A:
- SndBank body in genuine Wii U common_mp is 4760 B (one extra tail u32 vs
  mp_raid's 4756); loadedAssets offsets identical. Detect by which offset
  holds the FOLLOW name pointer, or key off zone name until pinned.
- The PC-side SndBank walk (mpl_raid.all) ends 46 KB short of the PC
  XANIMPARTS body; PC-only detail (OAT's PC reader is authoritative
  there), not chased.
- wiiu_zone.py mislabels console asset id 45 as LEADERBOARD; the genuine
  asset is XGLOBALS (xGlobalsSingleton). The console-id remap band around
  44..45 needs one insertion less than assumed.
- NOTE for WP-B (GfxWorld): between gfxworld_probe2's Wii U END
  (0x040a7ad0 in mp_raid) and the GameWorldMp body (0x040aa61d) sits a
  console-only ~11.6 KB block: SSkinShaders GX2 programs named
  gpuskin1bone..gpuskin4bone.glsl (siege-skin tail). It belongs to
  GfxWorld, not GameWorldMp. PC GfxWorld ends ~0x314 B after its probe END
  (lut materials + occluders) with no gpuskin block.

## Part B: GSC transcode (gsc_diff.py, tasks #15/#18)

The SCRIPTPARSETREE buffer is the complete compiled GSC container
(T6 GSCOBJ). Result: a PC GSC buffer converts to a byte-exact Wii U buffer
by byte-swapping alone. Opcodes are IDENTICAL numeric values; nothing is
remapped; scriptstring references do not exist inside the buffer (all
string references are buffer-internal offsets); there are no zone-level
fixups into the buffer (the SPT asset is a plain byte blob in the zone).

Verified: pc_gsc_to_console() produces byte-for-byte the genuine Wii U
buffer for 43/43 paired scripts (13 mp_raid + 30 common_mp), and
console_gsc_to_pc() inverts 43/43. Cross-zone check (PC zm_nuked ->
Wii U zm_transit _teamset_cdc): every differing byte is either linker
garbage inside alignment padding (91 bytes, functionally dead) or the
export checksum recomputed from that padding (8 bytes); zero unexplained.

Format (offsets in gsc_diff.py docstring): 0x40 header (magic
80 47 53 43 0D 0A 00 06, u32 crc + 8 u32 section offsets + u32 cseg_size +
6 u16 counts + u8s), strings (identical bytes both platforms), include
table (u32s), animtree table ({u16 name, u16 pad, u16 num, u16 pad, num x
{u32 anim-name offset, u32 code addr}}), exports (12 B {u32 checksum,
u32 address, u16 name, u8 params, u8 flags}), imports ({u16 name, u16
namespace, u16 num, u8 params, u8 flags, num x u32 addrs pointing at the
CALL OPCODE}), stringtablefixup ({u16 string, u8 num, u8 type, num x u32
addrs pointing at the aligned u16 operand}), and the cseg opcode stream.

cseg rules (all derived and byte-verified against 8,353 swapped operands):
- 1-byte opcodes, identical values on both platforms; operand table in
  gsc_diff.py OPS (GetByte u8, GetUnsignedShort u16, GetInteger/GetFloat
  u32, GetString/GetIString u16, GetVector 3xu32, GetFunction-family u32,
  field ops 0x20-0x22 u16 string offsets, jumps rel16 (including 0x3F),
  calls 0x2E/0x30/0x32/0x34 = u8 + aligned u32, SafeCreateLocalVariables
  0x17 = u8 count + count x u16 names, Switch 0x5A = aligned u32 count +
  count x {u32 value, u32 rel}, GetHash 0x5C u32, 0x59 u32, 0x5E u8,
  0x7B u16, 0x24 u8).
- Multi-byte operands align to their size relative to BUFFER START;
  alignment padding bytes are linker garbage, byte-identical only within
  the same zone build. Copy verbatim when transcoding; any value works
  when authoring.
- Each function is preceded by garbage pad to a 4-byte boundary plus one
  zero u32; export addresses are 4-aligned.
- export.checksum = zlib.crc32(function code bytes from the export address
  to the start of the next function prefix, seed 0). It covers the
  byte-swapped operands and interior padding, so it is platform-specific;
  gsc_diff recovers the exact code length by matching prefix crc32 against
  the source checksum, then rehashes the transformed bytes. Byte-derivable
  from PC in all 43 cases.

Boot-path conclusion (task #18): a working Wii U GSC does NOT need
authoring; PC-compiled GSC (shipped or compiled with any T6 PC-targeting
compiler) transcodes deterministically with pc_gsc_to_console(), including
the loader-checked export checksums. The only platform-specific residue is
alignment garbage, which is arbitrary. Combined with the SPT layout
(PC-identical, len+1 rule), injecting a transcoded script into a Wii U
zone is a pure payload swap.

## Files delivered
- Probes: scriptparsetree_probe.py, rawfile_probe.py,
  keyvaluepairs_probe.py, footstep_table_probe.py, leaderboard_probe.py
  (scanner, no genuine instances), gameworldmp_probe.py,
  destructibledef_probe.py, xanimparts_probe.py, sndbank_probe.py,
  gsc_diff.py (parser + pc_gsc_to_console/console_gsc_to_pc + verifier).
- Samples: console_scriptparsetree_sample.bin, console_rawfile_sample.bin,
  console_keyvaluepairs_sample.bin, console_footsteptable_sample.bin,
  console_gameworldmp_sample.bin, console_destructibledef_sample.bin,
  console_xanimparts_sample.bin, console_sndbank_sample.bin,
  gsc_pair_pc_mp_raid_fx.bin / gsc_pair_wiiu_mp_raid_fx.bin.
