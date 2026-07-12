# HANDOFF — PC DLC fastfile + ipak structure investigation (for Wii U conversion)

Exploratory research task for a fresh session. Goal: figure out **how PC DLC content partitions
between `.ff` (zone) and `.ipak` (streamed pak)**, because it's handled differently from stock PC
multiplayer maps (which are all-in-`.ff`, no per-map ipak), and determine **what that means for
converting a DLC map to Wii U** — specifically whether the DLC `.ff` holds assets that must be
repacked into ipaks, or whether it already works like Wii U (image pixels offloaded from the `.ff`
into ipaks).

Source dir (READ-ONLY — copy out before decrypt/parse, never write under E:\):
`E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all`

Use OAT (`tools/ref_oat` Unlinker) + the existing repo tools. Python w/ the repo:
`native_linker/`, `wiiu_ref/`, `tools/`.

---

## What the directory already shows (observed 2026-07-06)
Three distinct file classes coexist:

1. **DLC map `.ff` with NO per-map ipak** — the majority: `mp_bridge, mp_castaway, mp_concert,
   mp_dig, mp_downhill, mp_hydro, mp_magma, mp_mirage, mp_paintball, mp_pod, mp_skate, mp_studio,
   mp_takeoff, mp_uplink, mp_vertigo`, plus the zm/so maps (`zm_buried, zm_highrise, so_*`). Just a
   `.ff` (~30–70 MB).
2. **DLC map `.ff` + a matching per-map `.ipak`** — only a few: **`mp_frostbite.ff`+`mp_frostbite.ipak`
   (90 MB), `mp_nuketown_2020.ff`+`mp_nuketown_2020.ipak` (165 MB)**. Why do only these two carry
   their own ipak? (Both are special/bonus maps — investigate.)
3. **Big shared DLC-pack ipaks** — `dlc0.ipak`(107MB), `dlc1.ipak`(556MB), `dlc2`(437MB),
   `dlc3`(501MB), `dlc4`(464MB), `dlczm0..4.ipak`. These look like the DLC analog of stock
   `base.ipak`/`mp.ipak` — the shared streamed-texture store for a whole DLC pack.
4. **Tiny `_load_` pairs** — `dlc0_load_mp.ff`(2.8 KB)+`dlc0_load_mp.ipak`(688 KB),
   `dlczm0_load_zm.ff`+`.ipak`, and `dlcN_load_mp/zm.ff` (~3 KB each). Small → preload/manifest
   zones. Determine their role (asset-registration / stream-key manifest?).

## Prior context you MUST reuse (don't rebuild)
- **PC images stream from ipaks by nameHash — already solved & general.** `wiiu_ref/pc_image_enum.py`
  enumerates a PC `.ff`'s GfxImages; `wiiu_ref/ipak_stream.py` (`prepare`) pulls the pixels from PC
  ipaks via `ipak.PcImageSource` (keyed by platform-independent `nameHash = R_HashString(name)`),
  GX2-tiles them, and authors the Wii U ipak. **Validated byte-exact vs retail on mp_la (287/287).**
- **Key already-observed clue:** running the pipeline on **mp_skate** earlier resolved only 335/1029
  images and **skipped 392** — because the source ipaks were stock `base.ipak`/`mp.ipak`, NOT the
  DLC ipaks. That skip is almost certainly the DLC-ipak partition this task is about: mp_skate's DLC
  textures live in `dlc*.ipak`, not base/mp. Confirming this is basically the whole question.
- **The Wii U model (target):** on Wii U, GfxImage bodies in the `.ff` are streamed STUBS (328 B,
  1×1, streaming=1); the real pixels live in `base_split*/lowmip_split*` + a per-map ipak, keyed by
  (nameHash, dataHash). See `ipak_stream.scan_genuine_bodies` and the retail content dir.
- **The PC model (from earlier RE):** PC `.ff` GfxImage bodies (64 B) carry real dims but the pixel
  data is streamed from ipaks too (stock: base/mp.ipak). So PC and Wii U are conceptually the SAME
  offload model — the `.ff` holds zone+metadata, ipaks hold pixels. The DLC question is just **which
  ipak** a DLC map's pixels come from.

## The central question (state it precisely)
For a DLC map (say `mp_skate`), when converting to Wii U:
- (Q1) Does the DLC `.ff` hold any **pixel data inline** that must be repacked into a Wii U ipak, or
  are its GfxImages streamed stubs like stock maps (pixels entirely in ipaks)? → i.e. does DLC
  function like Wii U (fully offloaded) or does the `.ff` carry pixels?
- (Q2) **Which PC ipak(s)** source a given DLC map's image parts — the shared `dlcN.ipak`, the
  per-map ipak (only frostbite/nuketown), or a mix? Map each DLC pack (dlc0..4, dlczm0..4) to the
  maps it serves.
- (Q3) What are the `_load_` ff/ipak pairs, and do they need converting too (preload manifests /
  stream-key registration)?
- (Q4) For the two maps WITH a per-map ipak (frostbite, nuketown_2020): what's in the per-map ipak
  vs the shared `dlcN.ipak`? (Likely map-unique streamed parts vs shared — mirrors the Wii U
  base_split-vs-per-map split.)

## Hypotheses to confirm/refute (lead with these, then test)
- **H1 (most likely):** DLC works exactly like stock — `.ff` = zone + streamed GfxImage stubs,
  pixels in ipaks — the only difference is the pixels are in **`dlcN.ipak`** instead of base/mp.
  → Conversion is the EXISTING pipeline with `--pc-ipaks` pointed at the right `dlcN.ipak`(s). No new
  repacking of `.ff` assets needed. mp_skate's 392 skips resolve once dlc ipaks are in the source.
- **H2:** The per-map ipaks (frostbite/nuketown) hold map-unique parts the shared dlcN.ipak doesn't;
  a full conversion of those two needs BOTH the per-map ipak AND dlcN.ipak as sources.
- **H3:** `_load_` ffs are thin preload/registration zones (KVP/stream manifests), possibly needed
  so the engine knows the DLC stream keys — may need a Wii U analog or may be droppable.

## Concrete tasks (OAT + repo tools)
1. **Inventory the pairing.** Script the dir: for each `mp_*/zm_*/so_*` map, note ff size + whether a
   per-map ipak exists. Produce the map→pack table.
2. **What's in a DLC map `.ff`?** Copy `mp_bridge.ff` (no per-map ipak) out, decrypt with
   `tools/ff_decrypt.py`, and (a) `pc_image_enum.py` it — count GfxImages, check whether any are
   inline (pixels present) vs streamed stubs (answers Q1); (b) OAT `Unlinker --list` it to see the
   full asset-type breakdown. Repeat for `mp_frostbite.ff` (has per-map ipak) to compare.
3. **Confirm the ipak format + index the packs.** `ipak.IPak.read` on `dlc0_load_mp.ipak` (small,
   fast) to confirm it's the same IPAK container, then index `dlc*.ipak`/`dlczm*.ipak`: dump each
   pack's (nameHash, dataHash) entry set.
4. **Cross-reference.** Take `mp_skate`'s GfxImage nameHashes (from `pc_image_enum`) and find which
   pack(s) contain them (dlcN vs base/mp vs per-map). This directly answers Q2 and confirms/refutes
   H1 — and explains the earlier 392 skips.
5. **Re-run the pipeline with the right sources.** `ipak_stream.py prepare <meta> <out> --pc-ipaks
   <the dlcN.ipak(s) mp_skate needs>` and confirm the skip count drops toward 0. That's the practical
   proof of the conversion recipe.
6. **`_load_` ffs:** decrypt one, list assets, classify (answers Q3).

## Deliverable
A short findings doc: (a) the map→pack source table, (b) a clear answer to Q1 (does DLC `.ff` hold
pixels, or fully offloaded like Wii U — expected: offloaded, same as stock), (c) the conversion
recipe per DLC map (which ipaks to feed `prepare`), (d) the special-case handling for
frostbite/nuketown per-map ipaks, (e) what to do with `_load_` ffs. Update
`HANDOFF_native_converters.md` if it changes the image-source assumptions.

## Tools / rules
- `tools/ff_decrypt.py` (PC v147 decrypt), `wiiu_ref/pc_image_enum.py`, `wiiu_ref/ipak_stream.py`,
  `wiiu_ref/ipak.py` (`IPak.read`, `PcImageSource`), `tools/ref_oat` Unlinker (`--list`).
- ff_decrypt writes the zone NEXT TO its input → copy the `.ff` to scratchpad first (writing under
  E:\ is denied, correctly). Never edit under `E:\`.
- Expected bottom line before you even start: this is very likely H1 (DLC = stock offload model,
  just different source ipaks), which would make DLC conversion a **source-ipak wiring** change to
  the existing pipeline, not new `.ff`→ipak repacking. Prove it, quantify the exceptions.
