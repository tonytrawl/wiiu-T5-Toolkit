# HANDOFF: Convert PC `.sabs` / `.sabl` sound banks → Wii U (T6 / Black Ops 2)

## Mission
Build a converter that takes a **PC** Black Ops 2 `.sabs` (streamed sound bank) and
`.sabl` (loaded sound bank) and produces a **Wii U**-format equivalent the Wii U
game engine will load and play. This is the audio counterpart to the already-working
fastfile (`.ff`) and image (`.ipak`) PC→Wii U pipelines in this project.

Deliverable: a Python tool (fits alongside the existing `WiiU_FF_Studio/` tools) that
converts a PC `.sabs`/`.sabl` pair to Wii U format, plus a short findings writeup of
the format differences you had to bridge.

---

## ⛔ STRICT RULE — DO NOT EDIT ORIGINAL FILES
The directories below are **live game installs**. They are READ-ONLY references.
- **NEVER** write to, rename, move, or delete anything inside these folders:
  - `E:\Call of Duty Black Ops II\` (PC source)
  - `E:\Wii U Black ops 2\` (Wii U reference + target install)
- Always **copy** a file out to your own scratch/work directory before touching it.
- When you produce converted output, write it to a NEW work folder, never back into
  the game folders. The user will place finished files themselves.

---

## Where the files are (verified)

### PC (`.sabs` + `.sabl`) — SOURCE, read-only
```
E:\Call of Duty Black Ops II\pluto_t6_dlcs\sound\
    mpl_<map>.all.sabs      (streamed bank)
    mpl_<map>.all.sabl      (loaded bank)
    zmb_<map>.all.sabs / .sabl
```
(This is the only PC sound dir in the install — DLC + shared banks live here.)

### Wii U (`.sabs` + `.sabl`) — REFERENCE (target format), read-only
```
E:\Wii U Black ops 2\content\sound\                 <- *.all.sabs   (shared/streamed)
E:\Wii U Black ops 2\content\sound\loaded\          <- *.all.sabl   (shared/loaded)
E:\Wii U Black ops 2\content\english\sound\         <- *.english.sabs (localized)
E:\Wii U Black ops 2\content\english\sound\loaded\  <- *.english.sabl (localized loaded)
```

### ★ Matched "Rosetta" pair (same map, both platforms) — use this to diff the formats
```
PC   : E:\Call of Duty Black Ops II\pluto_t6_dlcs\sound\mpl_nuketown_2020.all.sabs   (8,800,256 B)
WiiU : E:\Wii U Black ops 2\content\sound\mpl_nuketown_2020.all.sabs                 (26,200,064 B)
```
Other maps present on BOTH sides (check by name) also work as pairs. The Wii U file
is ~3x larger for the same map → the per-entry audio is stored in a **different
(likely uncompressed/PCM or a Nintendo codec) codec** than PC. That size/codec
difference is the core of the job.

---

## What is already known about the format (starting point, verify everything)
Both platforms share the SAB container:
- Magic at offset 0x000 = `32 55 58 23` = **`2UX#`** (little-endian) on BOTH PC and Wii U.
- Header is **little-endian on both** (Wii U audio banks are NOT byte-swapped, unlike
  the `.ff` fastfiles which are big-endian — do not assume BE here).
- First header dwords of the nuketown_2020 pair:
  - PC : `2UX#` `0e000000 14000000 10000000 40000000 0a000000 08000000 ...`
  - WiiU: `2UX#` `0e000000 14000000 10000000 40000000 19000000 08000000 ...`
  - i.e. the dword at **offset 0x14 differs** (PC 0x0a vs WiiU 0x19) — likely a
    version/codec/asset-count field. Nearly everything else in the header matches.

This "2UX#" bank format is the T6 "SndBank"/"SABx" format. Known community references:
the format is a table-of-contents header + an array of sound-alias/entry records +
packed audio blobs. Your job is to map the record layout, identify the audio codec
field, and re-encode/repack PC entries into what the Wii U loader expects.

---

## Suggested approach
1. **Parse the header** on both PC and Wii U nuketown_2020 (LE). Enumerate the section
   table (offsets/counts). Name each field by comparing several maps.
2. **Parse the entry/record array.** Find per-sound records: name/hash, offset, size,
   channels, sample rate, **codec/format id**, loop points. Diff PC vs Wii U records
   for the same sound to see which fields change.
3. **Identify the audio codec difference.** PC T6 typically uses a mix of PCM/MSADPCM/
   XMA-ish or `.flac`-tagged blobs; Wii U likely uses PCM16 big-endian or a DSP-ADPCM
   (Nintendo) codec. Extract one blob from each side for the same sound and inspect.
   Determine whether Wii U wants: (a) raw PCM16 (endianness?), (b) DSP ADPCM, or
   (c) the same codec PC uses (then it's just header/record repack, no re-encode).
4. **Build the converter**: rewrite the header + record table into Wii U layout and,
   if needed, transcode each audio blob to the Wii U codec. Preserve names/hashes so
   aliases still resolve.
5. **Validate** structurally against a genuine Wii U bank (same section counts, record
   stride, alignment). The user will load-test in Cemu.

The `.sabl` (loaded) vs `.sabs` (streamed) likely share the record format; `.sabs`
references external stream data, `.sabl` embeds it. Handle both.

---

## Tools / environment
- Python 3.13 with `capstone` is available at:
  `C:\Users\Tony - Main Rig\AppData\Local\Programs\Python\Python313\python.exe`
  (note: the Git-Bash `python3` is a DIFFERENT interpreter without extra packages —
  call the Python313 exe explicitly for anything needing pip packages).
- Existing project tools to mirror style/placement: `...\Testing enviroment\WiiU_FF_Studio\`
  (`wiiu_ff.py` codec, `zone_validate.py`, `ff_assets.py`).
- Use a scratch dir for all work; copy inputs out of the game folders first.

## Guardrails / gotchas learned on this project
- Wii U fastfiles are big-endian v148, but these **audio banks appear little-endian** —
  confirm before swapping anything.
- Don't assume sizes; the Wii U bank being 3x larger means re-encoding, not just repack.
- Keep the sound **name hashes** identical across the conversion or aliases won't bind.
- Deliverable files go to a NEW folder; the user installs them into the game dirs.

## Report back
- The mapped `.sabs`/`.sabl` header + record structs (PC and Wii U).
- The codec bridge (what you had to transcode, or "repack only").
- The converter script + one converted sample bank for load-testing.
```
```
