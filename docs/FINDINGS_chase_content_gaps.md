# FINDINGS — CHASE session: content gaps from the raid gate (2026-07-09)

Companion to `HANDOFF_chase_content_gaps.md`. Everything below is validated on ≥2 maps
(mp_raid genuine pair + mp_dockside PC/WiiU pair). New files delivered:
`native_linker/gsc_swap.py`, `probe_gameworldmp_convert.py`, `probe_gameworldmp.py`.
Evidence dumps in `scratch_pairs/` and `scratch_gwmp_*.bin` (deletable).

**Headline: NONE of the four "content gaps" is a console layout divergence.** GSC is a
solved transcode; GameWorldMp and clipMap_t serialize IDENTICALLY on PC and console and the
gate numbers were converter/walker truncation artifacts; DestructibleDef/Glasses/no-pair
are allowlist classes. No stubs needed anywhere.

## 1. GSC endian-swapper — DONE, `native_linker/gsc_swap.py`
`wiiu_ref/gsc_diff.py` already held a verified opcode-level PC→WiiU GSC transcoder
(header/table/operand swap + export-crc32 recompute). `gsc_swap.py` wraps it at the
ScriptParseTree ASSET-BODY level: `convert_spt_body(pc_body) -> console body`
(12-byte struct BE + name + transcoded buffer + trailing NUL).
- Validated **13/13 raid + 17/17 dockside body-level byte-exact** (`python gsc_swap.py`,
  and with the dockside zone pair as args).
- The handoff's "code region MOSTLY equal" flag is fully explained: the only differing
  code bytes are aligned multi-byte cseg operands (u16/u32/vec3/lvars/switch payloads),
  all swapped by the opcode table; byte-exact results prove no unexplained bytes.
- **Integration**: in `produce_nobackbone`, route `ScriptParseTree` through
  `gsc_swap.convert_spt_body` instead of the P2C SIMPLE structural swap (which copies the
  GSC buffer as raw chars → the ×13 violations).

## 2. GameWorldMp "+66 KB" — NOT a layout gap; converter mis-width bug
- `wiiu_ref/gameworldmp_probe.Walker` walks the SAME header to **308076 bytes on BOTH**
  the PC zone (LE) and the genuine console zone (BE). Serialization is identical
  (nodes stride 144, pathlink stride 16 — the T6_Assets.h 12-byte pathlink def is wrong
  for zone serialization; basenodes RUNTIME → 0 file bytes).
- The gate's 241860 emit is a `pc_to_console` structural-swap bug: struct_layout
  mis-widths pathnode fields (first symptom: u32 `type` swapped as 2×u16 — diff at body
  byte 45) and its walk under-consumes by 66216.
- **`probe_gameworldmp_convert.py` is the executable conversion spec**: explicit field
  widths from `gameworldmp_t6_load_db.cpp` + T6_Assets.h (full table in its docstring).
  Result: **byte-exact vs genuine mod alias-pointer words** on raid (308076, 517 ptr
  words) AND dockside (759039, 675 ptr words).
- **Recommendation**: port the probe's `Conv` class into the pipeline as a dedicated
  GameWorldMp converter (like fx/xmodel). No stub needed — conversion is exact, so
  pathfinding data ships correctly for the playable tier.

## 3. clipMap_t — layouts IDENTICAL; gate sizes were DOUBLE truncation artifacts
- `clipmap_probe.walk` from the true body start yields **identical section boundaries
  and totals on PC and console**: raid 4,412,940 bytes (22 sections), dockside
  2,910,696 (23 sections, anchored via the worldspawn entity text). Zero mismatches.
- The gate's "2238640 vs 2238630" is BOTH sides under-walking at ~2.24 MB through the
  shared ZoneCode/struct_layout path (`console_spans`' ReEmitter and P2C respectively).
  The "many hard-diff bytes" were two differently-truncated streams compared to each other.
- **CRITICAL knock-on**: because `console_spans` truncates clipMap ~2.17 MB early, every
  console span AFTER asset 852 (raid: 853–888 techsets/materials/SPT/FX/sounds/xanims/
  footsteps/images) is misattributed garbage, and the zone's last ~15.6 MB
  (70511857..86174226) — which contains the REAL tail bodies (e.g. the compass techset
  name at 72933158) — is never reached. Gate results for tail assets are unreliable
  until this is fixed. Fix belongs in `raid_oracle_control.py`/walker (assemble session):
  dispatch clipMap_t extent to `clipmap_probe.walk` (console '>', same `_SIZES` +
  console material span), exactly as `clipmap_pc.py` does for PC.
- **Region classification** (word-class scan over all 4.4 MB, raid): every 4-byte word
  falls into {u32-swap, u16-pair-swap, raw-copy, b5-alias-pair} per section, EXCEPT
  166 words in staticModelList/cmodels that are same-exponent float-mantissa drift
  (delta ≤128 int-ulp, i.e. link-time recompute of placement bounds — same family as
  the FX float-LSB class) → allowlist class (c-none, allowlist-only).
  Per-section swap recipe (this IS the converter spec):
  | section | swap |
  |---|---|
  | body(332), brushsides, brushVerts, verts, visibility, box_brush | u32 (+b5 ptr words) |
  | materials | u32 + raw name chars |
  | leafbrushNodes, leafs | u32 + u16 arrays + raw |
  | uinds, triIndices, aabbTrees, nodes | u16-dominant (+u32 heads / b5) |
  | brushes, staticModelList, cmodels, dynEntDefList, constraints | u32 + few u16 (+b5; float-drift allowlist) |
  | triEdgeIsWalkable, partitions, mapEnts | raw bytes (+u32 words) |

## 4. DestructibleDef ×8 — float-LSB source-divergence allowlist
All non-pointer diff words across all 8 pairs are `|ours_word − gen_word| == 1`
(e.g. 0.05: 3d4ccccd PC vs 3d4ccccc console; 0.6 likewise) at fixed struct offsets
(@1636/@1948/...). DD7 additionally has UNALIGNED b5 alias pairs (byte offset ≡1 mod 4,
e.g. ours A01BD2A4 vs gen A0048F01 at word+1) — pointer class, loader-sim domain.
**Allowlist spec**: add `DestructibleDef` with rule "hard word allowed iff BE-int delta
== 1" (float-LSB class); unaligned-b5 windows go to semantic_diff's pointer handling.

## 5. Glasses 9654 vs 9622 — exactly the material −16 class, twice
Resync diff shows ALL diffs are 4-byte pointer/scriptstring substitutions EXCEPT exactly
two `ours+16` deletions (@7638 and @8046/8030), both inside nested inline Materials
(extra 16-byte textureTable row `88128812 e49e492c 18128922 0000000c` that genuine console
materials drop). 2×16 = 32 ✓ exact. **Fix/allowlist**: route GlassDef nested materials
through `material_convert` (which already implements the −16/−32 class), or allowlist
Glasses with "size delta == sum of nested-material −16/−32".

## 6. no-console-pair ×2 — console-ALIASED twins confirmed
Our PC list emits bodies for asset 854 TECHNIQUE_SET (`sw4_2d_compass_map_static_2feeq903`)
and 885 IMAGE. The genuine console asset list carries ALIASED header entries (headerPtr =
b5 alias, no inline body) in exactly the matching tail type slots (849 TECHNIQUE_SET;
883/885/886/888 IMAGE), and the compass techset content IS present in the console zone
(within the post-clipMap tail region the span walk currently never reaches).
**Pairing rule for the gate**: a PC body-bearing asset with no console body-pair PASSES if
the console list has a same-type ALIASED entry at the aligned list position (body defined
elsewhere in-zone). Caveat: alias b5 values do NOT map linearly to stream offsets
(runtime-block allocs consume virtual address space without file bytes — e.g. GameWorldMp
basenodes 878×16) — resolving them needs the loader-sim virtual cursor.

## Definition-of-done checklist
- gsc_swap.py 13/13 byte-exact + dockside 17/17 ✅
- GameWorldMp +66 KB decomposed → no gap; exact converter probe, raid+dockside ✅
- clipMap diffs classified per region; class (c) = float-drift allowlist only ✅
  (+ bonus root-cause: gate tail-span corruption)
- DestructibleDef / Glasses / no-pair → allowlist specs ✅
