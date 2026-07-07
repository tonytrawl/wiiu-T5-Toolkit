# BO2 `.sabs` / `.sabl` sound banks — PC → Wii U conversion notes

Findings from diffing `mpl_nuketown_2020` (and other maps) across
`E:\Call of Duty Black Ops II\pluto_t6_dlcs\sound\` (PC) and
`E:\Wii U Black ops 2\content\sound\` (Wii U). Converter: `sab_convert.py`.

## Container (identical on both platforms, ALL little-endian)

Unlike the fastfiles, the audio banks are **not** byte-swapped on Wii U.

```
SndAssetBankHeader (0x48 bytes):
  +0x00 u32   magic '2UX#'
  +0x04 u32   version        = 14
  +0x08 u32   entrySize      = 20
  +0x0C u32   checksumSize   = 16
  +0x10 u32   dependencySize = 64
  +0x14 u32   entryCount
  +0x18 u32   dependencyCount = 8
  +0x1C u32   pad
  +0x20 u64   fileSize
  +0x28 u64   entryOffset      (0x800-aligned, table sits near END of file)
  +0x30 u64   checksumOffset   (0x800-aligned)
  +0x38 u8[16] checksumChecksum = MD5(entryTable ++ checksumTable)   <- verified
+0x48: dependencyCount x 64-byte C-string bank names
0x800: packed audio blobs (contiguous, 8-byte aligned)

SndAssetBankEntry (20 bytes):
  u32 id          — SND_HashName of the alias name; MUST be preserved so
                    converted fastfile aliases still bind
  u32 size        — blob byte size
  u32 offset      — absolute file offset
  u32 frameCount  — sample count AT THE ORIGINAL 48 kHz rate (see below)
  u8  frameRateIndex (always 6 = 48000 in every bank on both platforms)
  u8  channelCount (1/2)
  u8  looping
  u8  format

checksum table: entryCount x MD5(blob)  — verified byte-exact.
```

## Format difference (the actual job)

| | PC | Wii U |
|---|---|---|
| `.sabs` (streamed) | format **8** = FLAC stream per entry | format **9** = Nintendo DSP-ADPCM |
| `.sabl` (loaded)   | format **0** = raw PCM16-LE          | format **9** = Nintendo DSP-ADPCM |

Every entry in every Wii U bank (mp/sp/zm, `.all` and `.english`, sabs and
sabl) is format 9, rateIdx 6.

**Wii U audio is resampled to 2/3 of the source rate (48000 → 32000 Hz)**
while `frameCount` keeps the *original 48 kHz* sample count. Confirmed by
decoding Wii U entry 0 of nuketown sabs and cross-correlating against the PC
FLAC resampled 2/3: normalized peak 0.998. (Genuine banks carry ~300 samples
of resampler latency and a few slack frames at the end; harmless.)

## Wii U format-9 blob layout

```
+0  u32 BE 0x12345678           (magic)
+4  u32    0                    (rarely 0x980 in genuine banks — unknown,
                                 seek/loop aux data; 0 works everywhere else)
+8  per channel (48 bytes each):
      s16 BE coef[16]           (8 DSP predictor pairs)
      u8[16] zero               (gain / initial & loop ps,hist — always 0)
then DSP-ADPCM frames, 8 bytes = 14 samples.
Stereo: one 8-byte frame per channel interleaved L,R,L,R,...
        (verified: L/R decode correlation 0.76 vs garbage for split layout)
Loops (looping=1) restart from the beginning; no loop context stored.
```

## Converter pipeline (`sab_convert.py`)

1. Parse PC bank, decode each entry (FLAC via libsndfile / raw PCM16).
2. `scipy.signal.resample_poly(pcm, 2, 3)` → 32 kHz.
3. Per channel: derive 8 DSP coefficient pairs and encode 14-sample frames
   (numba port of the canonical Nintendo `dspadpcm` encoder,
   `DSPCorrelateCoefs` + `DSPEncodeFrame`). Round-trip SNR 23–46 dB,
   matching genuine bank quality.
4. Repack: same ids/frameCounts/looping/deps, format=9, blobs from 0x800,
   entry+MD5 tables at the end, header checksum = MD5(entry++checksum tables).

Usage:
```
python sab_convert.py <pc.sabs> <pc.sabl> ... -o <out_dir>
```
Needs: numpy, scipy, soundfile, numba (all installed in Python313).

Converted banks are ~2.4x smaller than genuine Wii U ones only because the
Pluto DLC PC banks contain fewer entries (e.g. nuketown sabs: PC 10 streams
vs Wii U retail 25 — the retail Wii U bank also carries music streams that
PC keeps elsewhere); per-entry sizes match the codec math exactly.

## Open items

- The rare nonzero u32 at blob+4 (`0x980` on one nuketown music entry) is
  unidentified; we always write 0, which matches >99% of genuine entries.
- Load-test in Cemu pending (user).
