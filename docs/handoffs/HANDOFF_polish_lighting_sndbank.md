# HANDOFF — POLISH session: lighting repack + SndBank loadedAssets conversion

Standalone worker doc, 2026-07-10. Two bounded, independent RE items that run in PARALLEL with
the (active) runtime-interior assemble session. Both are playable-tier: neither blocks boot #1,
both are the first things needed after it. Do them in either order; they share no code.

## FILE OWNERSHIP (hard — an assemble session is running concurrently)
- You may CREATE new files only: `native_linker/lighting_repack*.py`,
  `native_linker/sndbank_audio*.py`, probe/diff scripts, findings docs.
- You may NOT edit: `produce_nobackbone.py`, `pc_to_console.py`, `smalls_convert.py`,
  `material_convert.py`, `raid_oracle_control.py`, `loader_sim*`, any `gfxworld_*.py`,
  `pc_walk.py`/`walker.py`/`struct_layout.py`, or existing geometry converter files.
  Deliver executable specs / new modules; the assemble session integrates.
- Never write under `E:\` (installed game). Copy zones out first.

---

## PART 1 — Lighting repack ("runs darker")
### Known state (don't re-derive)
Geometry is HW-confirmed on Cemu (`mp_raid_GEOMDIAG3/4`): positions/tris/UVs render correctly.
The registered defect is lighting-level: the converted map **renders darker** than genuine.
Suspects on record: **vertex tangent encoding** and the **vd1 vertex stream's V component**
(vd1 currently converts as a plain swap2). vd0 offset semantics are SOLVED
(`FINDINGS_offline_RE_vd0_offset.md`) — do not reopen them.
### Method (matched-pair oracle — raid has both PC and genuine console zones)
1. Locate paired vd1 streams (and any per-vertex normal/tangent/color fields in vd0) for the
   same surfaces PC↔genuine console. The proven walkers give exact spans.
2. Diff field-by-field: which components does swap2 NOT reproduce? Classify per-component
   (normal, tangent, lightmap UV, vertex color). Expect a packed-format difference (console
   10:10:10 or byte-normal repack is the likely class — cf. smodelDrawInsts' 10:10:10 axis
   discovery; try that encoding family first).
3. Derive the re-encode, validate **byte-exact vs genuine on raid + dockside** (both have
   oracles; the two-map rule applies).
4. Also check lightmap-adjacent data you now have contrast for: Track F's lightmap re-encode
   (RGBA8→BC3) is a REGISTERED lossy class in `CAVEATS_gfxworld_trackF.md` — do not chase BC3
   noise as a lighting bug; your target is the VERTEX stream fields.
### Deliverable
`lighting_repack.py` (or a findings doc + patch spec if the fix is a few lines in an owned
file): exact per-field conversion, 2-map byte-exact evidence, and a one-paragraph integration
note for the assemble session. If a Cemu A/B is wanted, build a GEOMDIAG-style raid artifact
the USER can boot — do not attempt to run Cemu yourself.

## PART 2 — SndBank loadedAssets → console format
### Known state (don't re-derive)
- PC `mpl_raid.all` = 59.7 MB; genuine console = 12.97 MB incl. an **11.5 MB inline
  loadedAssets blob**. The blob is **platform-format audio** (console wants DSP-ADPCM) — the
  "byte-identical" claim was overbroad and is retired (PROJECT_STATE + CAVEATS §8b). The
  non-loaded interior (alias tables etc.) IS verbatim-identical at identical relative offsets;
  the ~100 KB head is a field-aware swap the assemble side already handles.
- **Start from `sab_convert.py`** (wiiu_ref): the PC .sabs/.sabl → WiiU SAB converter already
  solved FLAC/PCM → 2/3-rate DSP-ADPCM encoding. The inline loadedAssets tracks are very
  likely the same track format inline'd — reuse the codec, don't rewrite it.
- Console also carries the localized bank `mpl_<map>.english` (raid 6,663 B, alias metadata
  only) — that's the ASSEMBLE session's authoring item, not yours; ignore it.
### Method
1. Parse the genuine console loadedAssets blob (raid): enumerate entries (count, name/hash,
   format tag, sizes, offsets). Cross-check entry metadata against the PC blob's entries —
   establish the PC-entry → console-entry mapping and which PC tracks got loaded vs streamed.
2. Decode one PC track, DSP-ADPCM-encode via the sab_convert path, compare structure (not
   bytes — lossy codec) against the genuine console entry: header fields, channel/rate/loop
   metadata, size arithmetic must match exactly; sample data judged by decode-back sanity.
3. Build `sndbank_audio_convert.py`: PC loadedAssets blob → console-format blob (entry table
   byte-exact vs genuine mod sample data; total size arithmetic consistent with the console
   physical-block header). Validate on raid + one more map with a console oracle.
### Deliverable
`sndbank_audio_convert.py` + findings doc: blob format spec, entry-mapping rule, validation
numbers, and the integration note (where the assemble's SndBank emit swaps in the converted
blob — spec only; they wire it).

---

## Bars & house rules
Byte-exact vs oracle for everything structural; lossy-codec sample data judged by metadata
exactness + decode-back. ≥2 maps for every rule (raid-luck-masking). Chase to root. Keep
findings docs honest; register any new lossy/divergence class in CAVEATS so boot/playtest
reads correctly. struct_layout is unreliable for console sizes — trust probes.

## Definition of done
Lighting: the darker-render defect root-caused to named vertex fields with a 2-map byte-exact
re-encode (or an evidence-backed finding that it is NOT vertex-stream data, with the real
locus named). SndBank: loadedAssets blob converts PC→console with byte-exact structure on 2
maps. Both with integration specs the assemble session can apply in minutes.
