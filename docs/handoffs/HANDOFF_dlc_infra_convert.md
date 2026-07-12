# HANDOFF — DLC infrastructure conversion + Wii U (Cemu) deployment

Standalone doc. Status of getting PC BO2 DLC **infrastructure** (shared image packs + the thin `_load_`
frontend fastfiles — **NOT the map `.ff`s**) onto Wii U / Cemu, and what the hardware told us.

This doc is **fact-first**: everything below is either **CONFIRMED** (observed this session) or explicitly
marked **UNKNOWN / UNVERIFIED**. Do not treat unknowns as settled.

---

## Ground-truth files (READ THESE FIRST for structure)

The single most useful reference we obtained is **genuine console DLC0 load fastfiles** (dumped from a
Wii U), alongside their **PC source** counterparts. Diffing them shows exactly how a converted load zone
*should* look.

| Role | Path |
|------|------|
| Genuine **console** `dlczm0_load_zm.ff` | `C:\Users\Tony - Main Rig\Downloads\dlczm0_load_zm.ff` |
| Genuine **console** `dlc0_load_mp.ff` | `C:\Users\Tony - Main Rig\Downloads\dlc0_load_mp.ff` |
| **PC source** `dlczm0_load_zm.ff` | `E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all\dlczm0_load_zm.ff` |
| **PC source** `dlc0_load_mp.ff` | `E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all\dlc0_load_mp.ff` |
| **Our converted** output (all load zones + ipaks) | `Testing enviroment\dlc loading\` |

Decrypt console `.ff` with `WiiU_FF_Studio/wiiu_ff.py` (`wiiu_ff.decrypt`), PC `.ff` with
`tools/ff_decrypt.py`. Asset index read via `wiiu_ref/wiiu_zone.py` (console) / `native_linker/pc_zone.py` (PC).

### CONFIRMED — asset-index structure (this is the important finding)

The PC source and the genuine console zone have the **same asset index**. Neither contains inline
`GfxImage` (type 8) assets — the materials reference images by hash, and those images are **streamed /
defined elsewhere**, not carried in the load zone.

```
                       KVP(49)  techset(7)  IMAGE(8)  MATERIAL(6)  SOUND(9)  RAWFILE(41)
dlczm0_load_zm  PC      1        1           0         4            1         1     (zone 13798 B)
dlczm0_load_zm  CONSOLE 1        1           0         4            1         1     (zone  9431 B)
dlczm0_load_zm  OURS    1        1           4         4            0         1     (WRONG)
dlc0_load_mp    PC      1        1           0         1            0         1     (zone  7865 B)
dlc0_load_mp    CONSOLE 1        1           0         1            0         1     (zone  2846 B)
dlc0_load_mp    OURS    1        1           1         1            0         1     (WRONG)
```

**Our converter diverges from ground truth in two ways:**
1. It **adds `IMAGE` (type 8) assets** to the load zone that neither the PC source nor the console build
   contain. (Introduced by the `ipak_stream.prepare` image-enumeration path in `convert_loadpair.py` +
   OAT re-embed; the plain OAT `--list` of the PC zone also shows these images, so OAT is expanding
   material→image references into top-level image assets.)
2. For the zm zone it originally **mangled/dropped the `SOUND` asset**; the console build **keeps** it.

A correct conversion must reproduce the console index: `KVP + techset + MATERIAL(s) (+ SOUND for zm) +
RAWFILE`, with **no** added image assets.

### UNKNOWN
- **Where the referenced `GfxImage` headers (`menu_zm_map_nuketown`, `loadscreen_*`, …) are defined on a
  real Wii U.** The load zone references them via materials but does not contain them. Not yet located
  (candidates to check: the DLC map content zone, `common_zm`, or an ipak-side registration — unverified).

---

## What is deployed right now (Cemu on this machine)

- **Cemu paths (CONFIRMED from the log's mount banner):**
  - Base game: `E:\Wii U Black ops 2` (NOT the `Downloads\...WUP` folder).
  - Update partition: `…\AppData\Roaming\Cemu\mlc01\usr\title\0005000e\1010cf00`.
  - DLC (AOC): `…\AppData\Roaming\Cemu\mlc01\usr\title\0005000c\1010cf00`.
- **AOC (DLC) title we created** — `…\mlc01\usr\title\0005000c\1010cf00\`:
  - `code\app.xml` (title_id `0005000C1010CF00`, app_type `0800000E`), `code\cos.xml` (cloned from update).
  - `meta\meta.xml` (title_id retargeted to `0005000C1010CF00`).
  - `content\0010\` — **21 converted Wii U ipaks**.
- **Load fastfiles** live in base `E:\Wii U Black ops 2\content\english\`.
- **Disabled/rolled-back load zones** backed up in `E:\Wii U Black ops 2\_dlc_zm_load_disabled\`.

### CONFIRMED behaviors
- Cemu mounts the AOC folder as DLC (`DLC: …\0005000c\1010cf00 [Folder]`) **only** when it is a complete
  folder title — `content` + `meta` alone were ignored; adding `code\app.xml`+`cos.xml` made it mount.
- The engine enumerates the AOC volume at **`/vol/aoc0005000c1010cf00/0010`** — so DLC ipaks must sit
  under `content\0010\`, not `content\`.
- Load `_load_` fastfiles are opened from the **base** volume `/vol/content/english/`, NOT the AOC volume.
- The engine (this build) requests **`dlc0_load_zm.ff`** (never `dlczm0_load_zm.ff` in any log) and a
  localization `en_dlc0_load_loc_zm.ff` (we do not have the latter; it returns `-6`, tolerated).
- The **DLC gate RPL patch** (`Content_PlayerHasDLCForMapPackIndex` → `li r3,1; blr`, located by symbol
  via `wiiu_ref/rpl_dlcgate_patch.py`) surfaced **DLC0 + DLC1** maps in the menus.
- The Wii U `mapsTable` contains rows for **DLC0 and DLC1 only** — DLC2/3/4 maps did not appear even
  with the gate open (their rows are not in the table).
- With **no** `dlc*_load_zm.ff` present, the **zombies menu loads without crashing** (the missing files
  return `-6` and are tolerated). => the zombie load zones are **not required** for the menu to run.

### CONFIRMED failure modes (the load-zone crashes)
- Our **converted** `dlc0_load_zm.ff` crashed the frontend. Fixes attempted, each moving the failure
  point further: techset null-shader (fixed via `OAT_TECHSET_DIR` + genuine `trivial_9z33feqw`),
  container-name mismatch (`wiiu_ff.pack` under `dlc0_load_zm`), soundbank body garbage
  (`OAT_DROP_TYPES=9`). After those, it still crashed while streaming.
- The **genuine console** zone repacked as `dlc0_load_zm` also fails: crashlog + `rpl_symbolize.py`
  show a **controlled `Sys_Error` on the DB_Thread** (fastfile loader), i.e. the loader deliberately
  rejects the zone. Stack: `FatalThreadFunc ← WiiU_FatalErrorHandler ← Sys_Error ← DB_Thread`.
- `OSReport` is **not captured** by Cemu for this retail build (0 lines even with coreinit logging on),
  so the `Sys_Error` **message string is not visible** — we do not yet know the exact reason.

### UNKNOWN / UNVERIFIED
- **The exact cause of the `Sys_Error`** when loading a (genuine or converted) zombie load zone. Not
  confirmed. Candidates NOT yet ruled in/out: the referenced `GfxImage` headers being absent; the
  `SOUND` asset's streamed bank being absent (`zmb_nuked_real_intro` is referenced; base game has
  `zmb_nuked_real`, not `..._intro` — presence of the exact bank is unverified); the internal name.
- **Result of the latest deploy**: the genuine zm zone renamed to `dlc0_load_zm` in **both** container
  and internal KVP asset name (with zone-header size fields corrected) is deployed but **not yet tested
  on hardware**.
- **Whether any DLC map actually boots when selected** — no DLC map `.ff` has been converted/deployed;
  the map-load path was never exercised.

---

## Tooling built / used this session

- **Whole-ipak PC→Wii U converter (new):** `Testing enviroment\...scratchpad\convert_ipak.py` — reads each
  PC ipak entry, parses the IWI, GX2-tiles via `ipak_stream.split_parts`/`tile_part_payload`, writes a
  big-endian Wii U ipak keyed `(name_hash, data_hash(payload,part))`. Converted all 14 remaining packs
  (dlc0–4, dlczm0–4, mp_frostbite, mp_nuketown_2020, zm_nuked, zm_nuked_patch) — 0 errors, all readback
  BE-valid. (NOTE: not hash-checked against any converted map `.ff`.)
- **Load-zone converter:** `...scratchpad\convert_loadpair.py` — enumerate images (`pc_image_enum`) →
  `ipak_stream.prepare` → OAT re-embed (`OAT_IMAGE_DIR` + `OAT_WRITE_WIIU` + `OAT_TECHSET_DIR` +
  `OAT_DROP_TYPES=9`) → `wiiu_ff.pack`. **This is the tool that adds the wrong image assets — needs
  rework** (see "correct approach" below).
- **DLC source-ipak resolver:** `native_linker/dlc_packs.py` (map→pack table + cross-ref fallback).
- **DLC-gate RPL patch:** `wiiu_ref/rpl_dlcgate_patch.py` (symbol-located, safe repack).
- **Relevant OAT env vars (in `Unlinker.exe`):** `OAT_WRITE_WIIU`, `OAT_REWRITE`, `OAT_IMAGE_DUMP/DIR`,
  `OAT_TECHSET_DIR` (inlines `<name>.techset` from a dir; corpus at `wiiu_ref/techset_corpus/`),
  `OAT_DROP_TYPES` (numeric asset-type id; `9` = SOUND — verify effect via `wiiu_zone` asset list, NOT
  string grep). `OAT_TECHSET_REF`/`OAT_TECHSET_SELFREF` exist but were not used.

---

## Correct approach (derived from the ground-truth diff — NOT yet implemented)

To make a load zone that matches the console structure:
1. Convert the PC load `.ff` **without adding image assets** — the output index must be
   `KVP + techset + MATERIAL(s) (+ SOUND for zm) + RAWFILE`, matching the genuine console zone. Determine
   how to stop OAT expanding material→image references into top-level `IMAGE` assets (or post-process the
   emitted zone to drop the type-8 assets and re-link the materials to reference the streamed images).
2. Preserve the `SOUND` asset with a valid console body (OAT's soundbank body was garbage — the genuine
   console `SOUND` body is the reference; a byte-diff against `C:\Users\...\Downloads\dlczm0_load_zm.ff`
   will show the correct layout).
3. Resolve **where the referenced `GfxImage` headers must come from** (open question above) — without
   them the materials have nothing to sample, which may be *why* the loader errors.
4. Match the name the engine requests (`dlc0_load_zm`) in **both** container header and internal asset
   name (a length-changing internal rename requires fixing the zone header `size` and `block_sizes[0]` —
   see `wiiu_zone.py` header: `u32 size, u32 externalSize, u32 blockSize[8]`).

**Or** side-step the frontend load zones entirely: they are confirmed **not required** for the menu, and
the maps themselves surface via `mapsTable` + the gate patch. The load zones only add loadscreen/menu art
and an intro sound.

---

## Out of scope / separate tracks
- **DLC map `.ff` conversion** (the actual playable maps) — not started; that is the full map-port pipeline.
- **`mapsTable` rows for DLC2/3/4** — registry work (`memory: wiiu-map-menu-registry`), needed for those
  packs to appear at all.
- The big shared ipaks are converted and deployed but **untested against a real map load**.

## Rules
Never write under `E:\...\pluto_t6_dlcs` (READ-ONLY PC source; copy `.ff` out before `ff_decrypt`, which
writes next to its input). The converted ipaks are large (~4.9 GB total). Cross-references:
`FINDINGS_dlc_ipak_investigation.md`, memory `dlc-ipak-partition`, `wiiu-map-menu-registry`,
`wiiu-sig-bypass`.

---

# UPDATE 2026-07-09 — NATIVE load-zone assembler (OAT path retired for load zones)

**`native_linker/assemble_loadzone.py`** replaces `convert_loadpair.py` for the `_load_` zones. It
authors a console zone natively (no OAT, no backbone) and is validated against both DLC0 oracles.

## Validation status (oracle byte-diff)
- **`dlc0_load_mp`: byte-identical to the genuine console zone except ONE header word** — block5
  (our writer-accounting figure 0xade vs linker 0xa21; ours is larger = safe over-allocation).
  KVP/techset/MATERIAL/RAWFILE bodies + container 100% byte-exact.
- **`dlczm0_load_zm`: 32 diff bytes in 6 understood regions** (see "zm gaps" below).
- **Converted `dlc1..4_load_mp.ff` written to `dlc loading\native\`** — each decrypts and
  round-trip-walks end-to-end. NOT yet Cemu-tested.

## Rules discovered (all oracle-derived, fact-checked this session)
1. **KVP**: console drops the ipak-registration pair (the one whose inline value == pack name,
   e.g. 'dlczm0'). Console does NOT register the DLC ipak via KVP.
2. **Techset**: every load zone (mp+zm, dlc0 both flavours) uses `trivial_9z33feqw`; the genuine
   2154B inline body is byte-identical between the zm and mp oracles at different offsets =>
   position-independent. Canonical blob: `wiiu_ref/trivial_9z33feqw_loadzone.techset`.
3. **Header**: size = zone_len - 40, externalSize = 0. block0 is a flavour constant
   (mp 0x1c8, zm 0x12ac — constant across ALL PC DLC load zones per flavour + both oracles).
   block5: ZoneWriter accounting over our own assembled zone (over-allocates slightly).
4. **No IMAGE assets** are added (the OAT bug is structurally impossible here — materials are
   converted natively and reference images by hash only).
5. **SndBank** (zm): PCConverter byte-swap gets ~99% —
   - bank path `.pc.snd` -> `.wiiu.snd` must be renamed on the PC zone BEFORE conversion;
   - `loadedAssets.zone/.language` @0x1264/0x1268 are empty-string aliases (linker content-dedup
     into arbitrary zero bytes) — repointed at the techset blob's zero run;
   - console adds one extra u32(0) immediately before the inline `raw\sound\...` path
     (= sndbank_probe's "common_mp 4760-byte body" open item, now explained);
   - @4752..: inline streamed-bank-name string region must be copied raw (walk u32-swaps it);
   - **the 16B block @body+2096 is the `.sab` header checksum (sab file offset 0x38)** — PROVEN:
     the PC zone value matches bytes @0x38 of `zmb_nuked_real_intro.all.sabs`. A converted zone
     must carry the checksum of the CONSOLE sab (ours: from sab_convert output).
## zm gaps (why zm ffs are NOT emitted yet)
   a. sab checksum 16B (above) + a 4B per-entry hash in `loadedAssets.entries` (PC value found
      inside the PC sab at the header-pointed section 0x2d2000) — both need our converted sab;
   b. one alias inside the entries region (PC 0xa0001e9d -> genuine 0xa0000b59; content-dedup
      into a material body — target semantics not yet decoded);
   c. two unaligned u16 swaps in the entries region (dynamic offsets).
## Material caveat (mp zones)
   dlc0's 5 oracle materials expose remaining `convert_material` deltas: the words are per-image
   GX2 metadata (dims like 0x2d0/720, format words, ipak-hash-looking refs) — the known
   "inline-material images" track. dlc1-4 mp materials carry PC-derived values there; the zones
   walk cleanly but the loadscreen art may not render/stream until the image-header sub-conversion
   is wired to the converted ipak metadata. Fix location: the diff table in this session's
   `loadzone_oracle_diff.py` (scratchpad) + `material_convert.convert_image`.

---

# UPDATE 2026-07-09 (session 2) — DLC0 ZM FRONTEND FULLY WORKING ON CEMU

**Menu art + zone + sound all load and RENDER.** Every step below is hw-confirmed on Cemu.

## The Sys_Error is SOLVED
`WiiU_FatalErrorHandler: ERROR: sound bank failed to load zmb_nuked_real_intro.all` — the
zombie load zone was never the problem. Two-stage cause:
1. the streamed bank file didn't exist on the console volume;
2. after deploying a converted bank: the engine VALIDATES the zone-embedded 16B checksum
   (SndBank body+2096) against the .sab header @0x38 -> mismatch = same fatal. A genuine
   zone can only run with the genuine console sab (which nobody has); a NATIVE-assembled
   zone embeds OUR converted sab's checksum (assemble_loadzone --sab) and loads clean.

## Menu images: full chain solved
- Streamed image bodies in load-zone materials MUST carry real GX2 metadata + the ipak
  part-hash table (material_convert.IMAGE_SOURCE / STREAMED_STYLE=(0,2) for menu images,
  GX2_TO_T6 format remap). Metadata-less stubs => checkerboard (engine never streams).
- The engine under Cemu NEVER lazily mounts AOC/DLC ipaks (nn_aoc is stubbed): it
  enumerates /vol/aoc.../0010 at boot and walks away. KVP pack registration, base-content
  copies, and <ffname>.ipak siblings all do NOT trigger a mount (all tested).
- **WORKING MECHANISM: base_split<N> probing.** The engine probes base_split1..N.ipak at
  every boot until a miss. A pak named base_split8.ipak is auto-mounted -> menu images
  stream from it. (dlczm0_load_zm.ipak as base_split8 rendered nuketown zm art.)
- AOC layout matters: with english/ + sound/ subfolders inside content/0010, the engine
  loads the load .ff and .sabs FROM THE AOC VOLUME (/vol/aoc.../0010/english/...).

## Batch build (native_linker/batch_loadzones.py)
Builds all 10 load ffs (5 mp + 5 zm incl. dlczm0->dlc0 rename), converts the 5 zm streamed
banks (rt_load/alcatraz/buried/tomb/nuked_real_intro), collects every embedded image entry
(material_convert.COLLECT_ENTRIES) and authors ONE merged base_split8.ipak (43 entries,
verified) whose hashes match the emitted zones BY CONSTRUCTION. Deployed: AOC english/ +
sound/ + base content base_split8.ipak.

## Open
- Engine only ever requests dlc0_load_zm.ff (and mp?) — dlc1..4 load ffs are deployed but
  never requested. Per-pack install detection (nn_aoc-based) is the remaining gate for
  DLC1-4 frontends; next: RE the pack-enumeration check near Content_PlayerHasDLCForMapPackIndex.
- SndBank dynamics leftovers (entries alias, 2 u16s) are hw-tolerated (zone loads+runs);
  fix opportunistically when generalizing.

---

# UPDATE 2026-07-09 (session 3) — DLC1 (DIE RISE) FRONTEND WORKING ON CEMU

**Die Rise loads and its menu art renders.** dlc1_load_zm.ff reaches the engine; 0 fatals.

## RPL patch (the DLC1-4 gate) — two patches, both on the UPDATE build
`C:\Users\...\Cemu\mlc01\usr\title\0005000e\1010cf00\code\t6mp_cafef_rpl.rpl`
(backups: .precontentpack.bak). Tools in wiiu_ref/:
1. rpl_dlcgate_patch.py — Content_PlayerHasDLCForMapPackIndex -> li r3,1 (surfaces DLC
   map ROWS from mapsTable; pre-existing).
2. rpl_loadgate_patch.py — **the key new one.** Patches the CALL SITE inside
   DB_LoadLoadFastfilesForNewContent: `bl Content_IsIndexedContentPackEnabled` -> `li r3,1`.
   The per-pack load loop then requests EVERY pack's `<id>_load_<mp|zm>.ff` (id from the
   static 9-entry table @VA 0x1013de3c: none/dlc0/dlczm0/dlc1/dlc2/dlc3/dlc4/dlc5/seasonpass).

## Why NOT patch __Content_DoWeHaveIndexedContentPack (the ownership fn)
Forcing DoWeHave->1 (or whitelist) makes packs "OWNED" globally. The ZM globe selector's
Content_GetEnabledContentPacks() calls DoWeHave per index and RENDERS each owned pack; a
pack with no hardware mapsTable geometry (dlc2-5/seasonpass, and even dlc1's map-pack model)
-> null deref -> GPU/render crash at the globe, BEFORE any load. CONFIRMED by reverting.
The fix insight: Content_IsIndexedContentPackEnabled has ONLY 2 callers, both in the DB
load path (DB_AnyContentLoadFastfilesPending, DB_LoadLoadFastfilesForNewContent) — the globe
does NOT use it. So the call-site patch loads the frontends WITHOUT marking packs owned ->
globe stays clean. DoWeHave left ORIGINAL.

## Deploy gotchas hit (all fixed)
- **Duplicate-asset Sys_Error**: `dlc0_load_zm` + `dlczm0_load_zm` both = nuketown zombies
  (dlc0_load_zm was an artificial rename) -> both define zmb_nuked_real_intro.all -> engine
  "Attempting to override asset" fatal. FIX: dlc0_load_zm is bogus for ZM (dlc0 = MP nuketown
  only); disable it EVERYWHERE (base content/english AND aoc/0010/english). Keep dlczm0_load_zm.
- **sab checksum Sys_Error**: the loader requests `dlczm0_load_zm` (stock name, index 2). The
  deployed dlczm0_load_zm.ff must be OUR NATIVE build (embeds OUR converted sab checksum), NOT
  the stock genuine zone (genuine checksum, which our converted sab can't match). Rebuild with
  assemble_loadzone --sab <ourconverted.sabs> and NO --rename (internal name stays dlczm0_load_zm).
- dlc2/3/4_load_zm currently disabled in aoc to isolate; re-enable once their maps have
  mapsTable rows + verified sabs (zmb_alcatraz/buried/tomb_load already converted+deployed).

## Working deploy layout (Cemu)
- AOC title 0005000c/1010cf00/content/0010/ : all ipaks + base_split8.ipak(64MB merged menu imgs)
  + english/ (native dlczm0_load_zm.ff, dlc1_load_zm.ff, dlc*_load_mp.ff) + sound/ (converted sabs)
- base_split8.ipak works from EITHER base content OR aoc/0010 (engine probes base_splitN at boot).
- Both rpl patches applied to the update-title t6mp_cafef_rpl.rpl.

---

# UPDATE 2026-07-09 (session 4) — ZM MAPSTABLE PARSED; Die Rise start grayed = ROW ABSENT

Die Rise (dlc1) frontend renders but "Start Match" is GRAYED. Root-caused it is NOT a
missing map .ff (SV_MapExists is stubbed `li r3,1`) and NOT the DLC gate
(LUI IsMapValid -> Content_PlayerHasDLCForMap, already patched true). It is the
**zm mapstable**: the zm_highrise row is ABSENT.

## Map table location + format (PARSED, tool: native_linker/mapstable_tool.py)
- Carrier: patch_zm.ff, StringTable asset **zm/mapstable.csv**.
- Struct: {name*, u32 cols, u32 rows, values*, cellIndex*} then inline name, then
  cells[rows*cols] each = {ptr u32, hash u32}, then the FOLLOW-cell string pool.
- Cell string resolution: hash = **djb2 case-insensitive** (h=5381; h=h*33+tolower(c)).
  A cell is: ptr==0 empty; ptr==FOLLOW inline string (sequential in pool); else an
  alias -> the string whose djb2 matches `hash` (zone-wide dedup; resolve by scanning
  all NUL-terminated strings in the zone and indexing by djb2, NOT by block offset —
  block5 base is per-span/non-constant).
- PC (LE) zm/mapstable = **20 cols x 10 rows**; WiiU (BE) = **19 cols x 4 rows**.
  WiiU omits PC's LAST column (compass position top/left).

## PC retail rows (the reference)  [col0 map | col3 nameKey | col5 idx | col11 DLCidx]
  R2 zm_transit(0/0) R3 zm_nuked(1/2) R4 **zm_highrise=Die Rise (2/3)** R5 zm_transit_dr(3/3)
  R6 zm_prison=MobOfDead(4/4) R7 zm_buried(5/5) R8 zm_tomb=Origins(6/6). R1 maxnum_map, R9 default.
  Col schema: 0 map, 1/2 factionShort, 3 nameKey, 4 signpostImg, 5 orderIdx, 6 descKey,
  7 compassOverlay, 8 size, 9 NO,10 YES, 11 DLCpackIdx, 12/13 factionNameKey, 14/15 factionId,
  16/17 coords, 18 0, [19 pos: PC only].

## WiiU zm/mapstable = ONLY zm_transit (maxnum_map=1). Die Rise/nuked/etc NOT present.
NEXT (rebuild, not yet done): inject zm_highrise row (PC R4 minus col19), bump maxnum_map
-> 2, rows 4->5. Rebuild StringTable (re-emit cells + dedup pool + djb2 hashes), repack
patch_zm.ff (grows -> OAT/native rebuild + 0x7FC0 codec + sig-bypass RPL). mapstable_tool.py
dumps LE or BE tables today; extend it to EMIT for the rebuild.

---

# UPDATE 2026-07-09 (session 4b) — MAPSTABLE DELIVERY PATH = OVERRIDE (no patch_zm rebuild)

## KEY: StringTable override is ALLOWED (patch_zm rebuild AVOIDED)
DB_LinkXAssetEntry (RPL @0x2230ecc) prints "Attempting to override asset" and Com_Errors
ONLY for types whose default-asset-name (table @VA 0x10130a24, indexed by console type id)
is EMPTY. Verified: SOUND default='' -> FATAL (our earlier crash); **STRINGTABLE (console
type 0x2b) default='mp/defaultStringTable.csv' (non-empty) -> OVERRIDE ALLOWED**. Also allowed:
explicit type set {7,0x11,0x1f,0x20,0x2a(RAWFILE),0x2e,0x30-0x33,0x3a-0x3c} and any type with a
non-empty default name (MATERIAL '$default', LOCALIZE 'CGAME_UNKNOWN', ...).
=> Deliver a NEW self-contained zm/mapstable.csv StringTable in a native zone WE emit (full
pointer control) that loads after patch_zm; it legally overrides. NO need to rebuild the 6MB
patch_zm.ff (whose structural walk diverges at asset ~100 = the Track G relink wall).

## StringTable emit format (console BE), for the emitter
{name* FOLLOW, u32 cols, u32 rows, values* FOLLOW, cellIndex* FOLLOW} then inline name,
then cells[rows*cols]={ptr u32, hash u32}, then FOLLOW-cell string pool (cell order), then
cellIndex[rows*cols] int16. Emit ALL cells as FOLLOW-inline (ptr=FOLLOW, hash=djb2ci(str),
inline string in pool) -> self-contained, no external aliases. Empty cell = FOLLOW + inline
"" (hash 0x1505). hash = djb2 case-insensitive (5381, *33, +tolower). cellIndex = sorted(
range(n), key=SIGNED hash asc) -- binary-search name lookup works (unique map-name hashes
resolve; empty 0x1505 cells group, tie-order irrelevant).

## WiiU zm/mapstable schema = 19 cols (PC has 20; WiiU drops last col = compass pos top/left).
Full DLC row set to emit (col0 map, col11 DLCidx): transit(0), zm_nuked(2), zm_highrise=Die
Rise(3), zm_transit_dr(3), zm_prison=MobOfDead(4), zm_buried(5), zm_tomb=Origins(6); bump
maxnum_map. PC rows saved: scratchpad/pc_zm_rows.json. Tool: native_linker/mapstable_tool.py.
NEXT: emitter -> add StringTable to a native load zone -> hardware test override + ungray Start.

## PREPPED (session 4b): all-maps mapstable emitted
native_linker/mapstable_emit.py -> `dlc loading/native/zm_mapstable_allmaps.stbl` (BE console
StringTable, 10 rows x 19 cols: header, maxnum_map=7, transit/nuked/highrise/transit_dr/prison/
buried/tomb, default). Self-checks via mapstable_tool. build_rows(maps=[...]) can subset.
REMAINING FINAL STEP: add this StringTable as an asset to a native load zone (assemble_loadzone
asset-list + body + name-in-stringtable) so it OVERRIDES patch_zm's zm/mapstable at frontend;
hardware-test (does the globe show all maps + Start ungray). Note map CONTENT (zm_highrise.ff etc.)
still not ported -> Start may still gate on map-installed once row exists; validate incrementally.

---

# UPDATE 2026-07-09 (session 4c) — MAP REGISTRATION MECHANISM FULLY MAPPED

## The globe / start-validity data flow (RPL RE)
- Globe DOTS = hardcoded start-loc list (LUI GetStartLocsZombie, static @0x113D37c0 stride
  0x548) -> Nuketown/Die Rise show regardless of tables.
- Map DATA / start-validity = a static map array (@~0x113D88F4, stride 0x70) built by
  **UI_LoadMaps** which reads **zm/mapstable.csv** via StringTable_GetAsset +
  StringTable_Lookup("maxnum_map"/"mappack_count"/per-row cols). GetMaps (LUI) + the
  Start-readiness path consume this array.
- Start button = LUI PartyHostIsReadyToStart: needs InParty + AreWeHost + lobby-ready flag
  @0x1037a73d. That flag is map-specific -> Tranzit (in the array) can Start; Die Rise/Nuketown
  (NOT in the array) stay grey. So the mapstable IS the right fix.

## Why our override didn't take (timing)
UI_LoadMaps callers: UI_InitOnceForAllClients (once, early) + Content_FoundContent. Our
rpl_loadgate_patch loads dlc1_load_zm (with the override StringTable) but BYPASSES
Content_FoundContent, so UI_LoadMaps is never re-run after our override links. UI_LoadMaps
already ran at init reading patch_zm's transit-only table -> array has only transit ->
Die Rise/Nuketown grey. StringTable override itself is valid + loaded (no fatal).

## To finish (options; NOT yet done)
1. Get the override StringTable linked BEFORE UI_InitOnceForAllClients (early-loading zone).
   Blocked: can't rebuild patch_zm/common_zm (relink wall); no early zone we control.
2. Re-run UI_LoadMaps after our zone loads (RPL call injection -> needs a code cave; none free).
3. Route through Content_FoundContent (calls UI_LoadMaps) WITHOUT the ownership globe-crash.
   Blocked: FoundContent needs the (empty) dlc package table + found flag.
CAVEAT regardless: map CONTENT (zm_highrise.ff etc.) is NOT ported -> even once selectable +
Start ungrayed, launching would fail at map load (separate full map-port pipeline).
Infrastructure built this session: mapstable_tool.py (parse), mapstable_emit.py (emit all-maps
StringTable), assemble_loadzone --add-mapstable (override-inject). Prepped: zm_mapstable_allmaps.stbl.

---

# UPDATE 2026-07-09 (session 4d) — OVERRIDE IS ZONE-PRIORITY-GATED; patch_zm file-replace is the path

## DB_LinkXAssetEntry override rule (full)
Allowed-type override does NOT last-wins: it compares DB_GetZonePriority(existing) vs
DB_GetZonePriority(new) and REPLACES only if new priority > existing (@0x2231270 bge=keep).
DB_GetZonePriority(zoneFlags @0x2230884) maps the zone's LOAD-FLAG bits -> a priority rank.
patch_zm = patch zone (high priority). Our dlc load zones load via
DB_LoadLoadFastfilesForNewContent with flag 0x80 (low) -> LOSES the priority contest.
=> our assemble_loadzone --add-mapstable override could NEVER win over patch_zm, regardless
of load timing. (Two independent blockers: low priority AND UI_LoadMaps ran at init.)

## Correct path (user's call, confirmed by RE): FILE-REPLACE patch_zm via the DLC folder
Put a modified patch_zm.ff in the AOC/override folder so the engine loads OURS as THE patch_zm
(high priority, early, before UI_InitOnceForAllClients -> UI_LoadMaps reads our table). No
asset-link override, no priority contest, no timing issue.
BLOCKER (the real one): building that patch_zm.ff = grow the zm/mapstable StringTable (+rows)
-> shifts all block-5 data after it -> needs full zone relink. Our structural walker (ReEmitter)
DIVERGES on patch_zm (silently mis-tracks among its 1600 assets; surfaces as OOB cursor at
asset ~99 RawFile). This is the Track G loader-simulation pointer-relink wall. Solving it =
make the walker traverse patch_zm's full asset variety (LOCALIZE_ENTRY x979, RAWFILE x345,
SCRIPTPARSETREE x183, MENULIST, XGLOBALS, etc.) byte-identically, then splice the grown
StringTable + shift + relink block-5 aliases past the insert. Substantial but it is the SAME
capability the whole console-linker effort needs.
