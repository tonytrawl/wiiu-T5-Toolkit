# BO2 Xbox 360 → Wii U Fastfile — Technical Findings

> **Current state (2026-07-01).** The container, block policy, enum remap, and BE serialization below are
> all validated. Since this doc was first written, three things advanced substantially: (1) **MAP_ENTS is
> console id 47** and **GSC is the map crash wall** (both hardware-confirmed); (2) **geometry** decoded to a
> **24-byte vertex, big-endian float32 xyz** (console `XSurface`=64B — the ID3D11 GPU handles are dropped);
> (3) a **native pure-Python unlinker** (`wiiu_ref/`) now reads all 889 assets and parses the data tier
> byte-exact, with console struct divergences (`Glasses`=16, `MaterialTechniqueSet.techniques[32]`, the
> ID3D11-drop rule) being derived and verified one type at a time. See **[NEXT_STEPS.md](NEXT_STEPS.md)** for
> the live roadmap and the memory notes for the native-unlinker detail.

Everything learned so far about converting *Call of Duty: Black Ops II* fastfiles
from Xbox 360 to Wii U. Goal: run unreleased Wii U DLC (focus: **Nuketown Zombies**)
by converting the existing Xbox 360 content. IPAKs already load on the user's setup;
the fastfile (`.ff`) is the missing piece.

\---

## 1\. Platform matrix

|Platform|FF magic|Version|Endian|Compression|Memory / PHYSICAL block|
|-|-|-|-|-|-|
|Xbox 360|`TAffx100`|**146**|big|**XMemCompress (LZX)**|split-ish, uses PHYSICAL|
|PS3|`TAff?100`|**146**|big|(LZX/zlib)|split (Cell+RSX), uses PHYSICAL|
|PC|`TAff0100`|**147**|little|zlib/deflate|uses PHYSICAL|
|**Wii U**|`TAff0100`|**148**|big|**zlib/deflate**|unified, **PHYSICAL = 0**|

Key takeaways:

* **360 and PS3 are both version 146** and big-endian → interchangeable as a source; neither is closer to Wii U.
* **Wii U (148) is the structural outlier** — it's the only build that puts everything in the VIRTUAL block (PHYSICAL = 0). This is a deliberate v148 build choice, not forced by hardware (the 360 has unified memory yet still uses PHYSICAL).
* **360 → Wii U avoids an endianness swap** (both big-endian); PC → Wii U would require byte-swapping every struct.

\---

## 2\. Encryption (Salsa20)

All signed fastfiles use **Salsa20** with a per-platform 256-bit key, 4 interleaved
streams, and a per-file IV derived from the zone name and advanced by a SHA-1 hash chain.

**Keys (from OpenAssetTools `ZoneConstantsT6.h`):**

* **Wii U** (supplied by user):
`B3 BD 6B 2C 82 42 8D 11 B8 88 2D 4C 6D 18 CC 79 E2 70 9F 6B D4 39 91 35 FD DE 14 E6 8F 3A BC CE`
* **Xbox 360 (Xenon):**
`0E 50 F4 9F 41 23 17 09 60 38 66 56 22 DD 09 13 32 A2 09 BA 0A 05 A0 0E 13 77 CE DB 0A 3C B1 D3`
* **PC:**
`64 1D 8A 2F E3 1D 3A A6 36 22 BB C9 CE 85 87 22 9D 42 B0 F8 ED 9B 92 41 30 BF 88 B6 5E DC 50 BE`

The internal **zone name seeds the IV**, so a repacked file's name must match what the
game loads it by (normally the filename without `.ff`), or decryption produces garbage.

\---

## 3\. Fastfile header layout

|Offset|Field|Notes|
|-|-|-|
|`0x00`|magic\[8]|`TAff0100` (Wii U/PC) / `TAffx100` (360)|
|`0x08`|version (u32)|146 / 147 / 148|
|`0x0C`|auth magic\[8]|`PHEEBs71` (signed marker)|
|`0x14`|flags (u32)|0|
|`0x18`|zone name\[32]|null-padded|
|`0x38`|RSA-2048 signature\[256]|—|
|`0x138`|chunk stream|`\[u32 size]\[payload]` …, terminated by `size == 0`|

**Chunk stream rules (validated):**

* Each chunk is **compressed, then Salsa20-encrypted**.
* Chunk `i` belongs to stream `i % 4`; IV comes from the hash chain for that stream.
* The 4-byte size field must not straddle a `0x80000` super-block boundary (pad with zeros to the boundary).
* **Each chunk must decompress to ≤ `0x8000` (32 KB)** — the console has a fixed per-chunk decompression buffer. Treyarch uses \~`0x8000` uncompressed blocks (max compressed `0x7DFF`).
* The file is **zero-padded to a `0x40` boundary** at the end.

\---

## 4\. Decompressed zone layout

```
u32 size                 # total stream size
u32 externalSize
u32 blockSize\[8]         # TEMP, RUNTIME\_VIRTUAL, RUNTIME\_PHYSICAL, DELAY\_VIRTUAL,
                         # DELAY\_PHYSICAL, VIRTUAL, PHYSICAL, STREAMER\_RESERVE
--- XAssetList (24 bytes) ---
u32 stringCount;  ptr strings
u32 dependCount;  ptr depends
u32 assetCount;   ptr assets
--- inline ---
script string pointer array (stringCount × 4), then null-terminated strings
asset directory: assetCount × { u32 type, u32 ptr }
per-asset data (interleaved)
```

* Pointers: `0` = null, `0xFFFFFFFF` = "data follows inline", other = block-tagged back-reference.
* **`OFFSET\_BLOCK\_BIT\_COUNT = 3`** — pointers encode a 3-bit block index (8 blocks). `INSERT\_BLOCK = VIRTUAL`. "Follows-inline" data is assigned to a block by **loader code (PushBlock)**, not by a tag in the stored pointer; only back-references carry the block tag.

`common\_mp` block sizes observed:

* **Wii U v148:** VIRTUAL = 136 MB, PHYSICAL = **0**
* **360 v146:** VIRTUAL = 102 MB, PHYSICAL = **1.7 MB**

\---

## 5\. Asset-type enum

* **360 (v146) and Wii U (v148) share the SAME asset-type enum** — content-stable types sit at identical type IDs. So 360 → Wii U needs **no type-ID remapping**.
* **PC (v147) is the outlier** (a `+1/+2` shift from the consoles). Do not use PC enum IDs to interpret console zones.
* Enum base: `ASSET\_TYPE\_XMODELPIECES = 0` … `ASSET\_TYPE\_ZBARRIER`. GSC = `ScriptParseTree`.

\---

## 6\. Bugs found \& fixed

### 6.1 LZX uncompressed-block padding (in OpenAssetTools)

OAT's vendored cabextract-era LZX decoder padded **odd-length uncompressed blocks** to a
16-bit boundary (correct for CAB/WIM LZX) — but **Xbox XMemCompress does not pad them**.
This desynced the rare high-entropy chunks (3 of 3174 in `common\_mp`). **Fix:** remove the
`if (block\_length \& 1) inpos++;` after uncompressed blocks (kept `INIT\_BITSTREAM`). Also
aligned the uncompressed-block start to libmspack semantics. After the fix, full 360 zones
decompress with 0 errors. (Worth a PR to OAT.)

### 6.2 Oversized repack chunks (in my packer)

My `ff\_pack` initially used `0x10000` (64 KB) uncompressed blocks → chunks decompressed to
64 KB, overflowing the console's fixed `0x8000` (32 KB) buffer → freeze. My Python decryptor
never caught it (it inflates dynamically). **Fix:** `UNCOMPRESSED\_BLOCK = 0x8000` and add the
`0x40` trailing zero padding. Validated: a round-trip of the genuine Wii U `common\_mp` now
runs on hardware.

\---

## 7\. Asset structure cross-check (360 vs Wii U `common\_mp`)

* **Identical** script-string tables (1187 inline strings, same text), asset directory at the
same offset (`0x6191`) → the format/framing is aligned.
* **Different:** header block sizes (PHYSICAL), asset counts (6160 vs 6272 — real content
difference), and per-asset data.

\---

## 8\. Crash cause — RESOLVED: the TEMP block policy

The early load crash is **not** signing, framing, the packer, endianness, the asset enum, or My
serialization — all proven correct. It is the **block policy**, specifically the **TEMP block**.

Comparing the **same map (`mp\_dockside`) across PC / 360 / Wii U**, and TEMP across 8 genuine Wii U
zones:

|Block|PC|Xbox 360|Wii U|
|-|-|-|-|
|**TEMP**|**12.6 MB**|**0x12ac**|**0x12ac** (constant across maps; zm `0xa5c`, weapons `0x24`)|
|RT\_PHYSICAL|0|0x900000|0xc60000 (constant; GPU scratch)|
|VIRTUAL|bulk|bulk|bulk|

**PC dumps persistent asset data into the file-backed TEMP block; both consoles keep TEMP tiny and
place that data in VIRTUAL** (+ a fixed RT\_PHYSICAL reservation). A PC-derived zone declares
megabytes of TEMP, which overflows the Wii U loader's fixed \~4.7 KB TEMP buffer → **crash on the
first 0x80000 super-block** (verified on hardware; the engine reads exactly one super-block and dies).

The earlier "PHYSICAL → VIRTUAL" theory was wrong/incomplete — the real, constant-across-platforms
difference is **TEMP**, and on 360 the data also spreads into RUNTIME/PHYSICAL/STREAMER blocks.

## 9\. My serialization is correct (validated in software)

OAT was extended to **write** big-endian v148 zones (byte-swap scalars/arrays/encoded pointers,
PC→console enum remap, BE header/block sizes). A PC-policy BE v148 zone **round-trips byte-perfectly**
through my OAT loader — all assets, 0 errors. So byte-swap, enum remap, and pointer encoding are all
correct; the only thing wrong with a converted zone is the **block layout** (§8).

## 10\. OAT now reads genuine Wii U fastfiles

`ZoneLoaderFactoryT6` now detects Wii U (`TAff0100` + big-endian version 148), with
`SALSA20\_KEY\_TREYARCH\_WIIU` wired in. OAT decrypts + decompresses + **parses** real Wii U zones
through the full data tier (stops at a GPU-asset `RUNTIME\_PHYSICAL` back-reference — the GPU wall).
This is the ground-truth reference for the correct console block layout.

## 11\. The block-relocation problem

The naive "redirect TEMP→VIRTUAL" remap is **architecturally broken**: OAT loads 32-bit zones into a
64-bit host by relocating pointer arrays **out-of-block** (alias table), kept separate from main block
data. Merging TEMP into VIRTUAL collapses that separation → in-block (writer) vs out-of-block (loader)
offsets drift → aliased pointers resolve wrong (traced via `OAT\_DBG\_ALIAS`). The fix must assign
blocks **natively** (codegen conditional `set block`) or **relocate via metadata** (rewrite header
block sizes + back-ref block tags only). See `NEXT\_STEPS.md`.

## 12\. GPU assets are platform-specific (the wall behind block policy)

Console vertex buffers are 32 bytes/vertex like PC but **not the same byte layout** (Latte attribute
packing); `TechniqueSet`s are PC D3D shaders. So `GfxWorld`/`XModel`/`SkinnedVerts` need per-vertex
re-encoding and techsets should be referenced from the Wii U base game. **Textures are not in the
`.ff`** (IPAK stream, already working), so texture format is not part of this problem.

See `TEST\_RESULTS.md` for the test chronology, `WIIU\_MAP\_CONVERSION.md` for the PC-map path, and
`NEXT\_STEPS.md` for the roadmap.

