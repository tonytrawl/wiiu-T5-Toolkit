# FINDINGS — SndBank loadedAssets (POLISH session, 2026-07-10)

## ⭐ The handoff premise is RETIRED: the in-zone blob is NOT audio

The "11.5 MB inline loadedAssets blob" in the genuine console mp_raid zone is **all zeros** —
entry table (654 × 20 B) and data (11,519,896 B) alike. 2-map validated: genuine common_mp
(`common.all` bank, 810 entries + 23,951,128 B) is also 100% zeros. It is a **runtime-filled
buffer allocation**, not platform-format audio. The PC zone's same region contains
unparseable garbage = uninitialized linker heap (PC's linker didn't zero it; console's did).
OAT's loader source confirms the semantics (`LoaderSoundBankT6.cpp`): `entries`/`data` are
plain `Alloc` capacity, `runtimeAssetLoad = true`, `dataSize` = the data size of the WRITTEN
loaded bank file.

**There is no PC→console blob conversion to do.** The audio lives in FILES:
- console loads `content/sound/loaded/<bank>.all.sabl` (loaded) + `content/sound/<bank>.all.sabs`
  (streamed); PC uses `sound/<bank>.all.sabl/.sabs`.
- PC→console file conversion was ALREADY SOLVED by `WiiU_FF_Studio/sab_convert.py`
  (PCM16/FLAC → 2/3-rate DSP-ADPCM format 9).

## Deliverable

`native_linker/sndbank_audio_convert.py`:
- `convert_map_banks(map, pc_sound_dir, out_dir)` — converts the map's .sabl/.sabs via
  sab_convert (console placement: .sabl → `content/sound/loaded/`, .sabs → `content/sound/`).
- `find_sndbank_body(zone_bytes, endian)` — locates SndBank bodies + loadedAssets fields by
  signature (validated on PC mp_raid/common_mp/mp_skate and both WU oracles).
- `console_zone_fields(pc_ec, pc_ds)` — the zone authoring numbers (spec below).
Probes: `sndbank_audio_probe*.py`.

## Zone authoring spec (assemble session)

| field | rule | evidence |
|---|---|---|
| entryCount | copy PC verbatim | see delta note below |
| dataSize | `align2048(PC_dataSize × 0.21)` | genuine console/PC ratio = **0.1972** (raid: 11,519,896 / 58,421,162) and **0.1948** (common: 23,951,128 / 122,939,726) — the PCM-48k→DSP-ADPCM-32k size ratio, consistent across both oracles; 0.21 adds ~7% headroom |
| entries / data bytes | ZEROS | genuine is zeros on both maps |
| rest of loadedAssets head | the field-aware swap assemble already does | unchanged |

Copying the PC dataSize verbatim also boots (capacity semantics — need ≤ capacity) but wastes
~80% of the buffer (mp_skate: PC dataSize 48,464,182 → ~10.2 MB console-sized vs 48.5 MB).

mp_skate measured (PC zone `mpl_skate.all` body @0x6c6d566): aliasLists=2492,
entryCount=599, dataSize=48,464,182 → console entryCount=599, dataSize=10,178,560.
PC bank files exist: `E:\pluto_t6_full_game\sound\mpl_skate.all.sabl` (3.9 MB) + `.sabs` (7.7 MB).

## Registered caveats / open items

1. **entryCount console delta (+2/+3):** genuine console raid = 654 vs PC 652; common = 810 vs
   PC 807. The exact genuine counting rule was NOT reproduced (tested: loaded-unique 542,
   loaded|primed-unique 784, minus-common 747 — none hit 652). The deltas are console-added
   aliases we don't ship; since the runtime fills entries only for aliases present in OUR
   (PC-copied) alias table, the PC count is self-consistent capacity. If a boot ever hits an
   entry-table overflow, bump entryCount by +8.
2. **SAB entry ids are not zone assetIds** on either platform (genuine console .sabl ids don't
   appear in the WU zone's alias assetIds; same on PC; pluto's rebuilt banks use synthetic
   arithmetic-progression ids). Runtime lookup evidently does not require id == assetId, so
   sab_convert's id-preserved-verbatim behaviour is correct. Do NOT "fix" ids to SND_HashName.
3. **No retail PC mpl_raid bank available** (only Plutonium's rebuild, different ids), so a
   byte-level entry-table diff of converted-vs-genuine console .sabl was not possible. The
   structural spec (container header, 20B entries, format-9 blob layout) was previously
   validated in SAB_FORMAT_NOTES.md / sab_convert; genuine console .sabl/.sabs parse cleanly
   with the same reader (12 + 2 entries for raid, format 9, rate_idx 6, 2/3-rate frame
   arithmetic consistent).
4. Console loaded-bank naming: WU common_mp uses `common.all` where PC uses `mpl_common.all`
   (map banks match: `mpl_raid.all` both). Only relevant if converting common_mp itself.
5. `mpl_<map>.english` (alias-metadata-only localized bank) remains the assemble session's
   authoring item, untouched here.

## Console blob-size arithmetic (if ever needed per-entry)

Console format-9 blob size is exactly predictable from PC entry metadata:
`8 + 48*ch + ceil(ceil(frames*2/3)/14)*8*ch` (magic+pad, per-channel 32B coefs + 16B state,
8-byte frames of 14 samples, stereo frame-interleaved) — matches sab_convert's writer.
