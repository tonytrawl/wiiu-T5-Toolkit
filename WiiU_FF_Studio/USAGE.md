# Wii U Fastfile Studio — Usage

## Install / run

No dependencies for the core tools. With Python 3.9+ on PATH:

```
python wiiu_ff_studio.py
```

Every tab logs to the **Output log** panel at the bottom; long jobs run on a
background thread so the window stays responsive.

---

## Tabs

### Decrypt  (Fastfile → Zone)
1. **Wii U fastfile** — pick the `.ff`.
2. **Output zone** — where to write the decompressed `.zone` (defaults next to the input).
3. **Decrypt + Decompress**.

Verifies the header is Wii U (v148) first, then writes the raw decompressed zone and
reports the internal name, chunk count and size.

### Repack  (Zone → Fastfile)
1. **Zone** — the decompressed `.zone`.
2. **Internal name** — auto-filled from the file name; **this must match the slot the
   game loads it as** (e.g. if you're replacing `mp_raid`, the internal name must be
   `mp_raid`, regardless of the file name on disk).
3. **Output fastfile** — where to write the `.ff`.
4. **Pack Fastfile**.

### Validate
1. **Zone** — the `.zone` to check.
2. **Reference (optional)** — a genuine Wii U `.zone` to diff header/conventions against.
3. **Validate Zone**.

Reports any structural divergence from genuine Wii U conventions (oversized/zero `TEMP`,
broken follow-pointers, malformed script-string table, invalid asset-directory entries).
Green "VALIDATION PASSED" means the structure matches what the loader expects.

### Zone editor  (browse & edit a zone)
1. **Zone** — pick a decompressed `.zone`, then **Open**.
2. The list fills with every editable asset found in the zone — the **scripts**
   (compiled GSC/CSC) and **rawfiles** — with their kind, byte size and name.
3. Select one and:
   * **Export selected** — save the raw blob to disk (decompile / inspect / edit it
     with your GSC tooling of choice).
   * **Replace selected (in-place)** — load a replacement blob back in.
4. **Save zone** — write the edited `.zone`, then run it through **Repack**.

> **Length rule:** an in-place replacement must be the **exact same byte length** as
> the original. The zone is a sequential stream with offsets baked into pointers, so a
> different length would shift everything after it and corrupt the graph. To resize a
> script, recompile it to the same length, or rebuild the zone through the OAT
> `OAT_GSC_DIR` inject path (which re-serializes and handles arbitrary lengths).

### OAT: Write Wii U Zone
Requires the extended OpenAssetTools `Unlinker.exe`.
1. **Unlinker.exe** — path to the build (auto-detected if you put it in `oat\`).
2. **Source fastfile** — the input `.ff`.
3. Options:
   * *Ignore signature check* — read unsigned / rebuilt fastfiles.
   * *Reserve RUNTIME_PHYSICAL block* — writes the fixed `0xc60000` reservation.
   * *Drop script assets* — omit `scriptparsetree` assets.
4. **Write Wii U Zone** → produces `<name>_rewrite.ff`, a **raw v148 zone**.
   Run it through **Repack** to get a loadable `.ff`.

Block-policy remap, inline-image stripping and the asset-type / `MAP_ENTS` remap are
applied automatically by the write path.

### OAT: Read Assets
Reads the assets in a genuine big-endian Wii U (v148) fastfile through the console read
path, which parses the Wii U console struct layouts that differ from the PC layouts.
1. **Unlinker.exe** and **Source fastfile** as above.
2. Options:
   * *Wii U console read path* — enables the block remap and the console struct layouts
     (Material 104 B, GX2 GfxImage 328 B, technique / GX2 vertex+pixel-shader chain).
     Leave on for genuine Wii U fastfiles.
   * *Ignore signature check* — read unsigned / rebuilt fastfiles.
3. **Read Assets** — the asset trace streams to the log.

> The console read is not yet complete for a whole zone; it currently stops at a known
> cross-material alias in the GPU-asset tier. It still reads far into a genuine zone
> (localize, material, GX2 image and technique/shader assets).

### OAT: Dump Zone
1. **Unlinker.exe** and **Source fastfile** as above.
2. **Output .bin** — where to write the decompressed content.
3. **Dump Decompressed Zone**.

Writes the raw decompressed content straight from the loading stream — useful for
byte-level inspection even when the asset graph can't be fully parsed.

---

## Command line

The same functionality without the GUI:

```
python wiiu_ff.py decrypt <in.ff> [out.zone]
python wiiu_ff.py pack    <in.zone> <name> [out.ff]
python zone_validate.py   <zone> [--ref <genuine.zone>]
```

OAT env flags (set them when invoking `Unlinker.exe --list <file>.ff`):

| Flag | Effect |
|------|--------|
| `OAT_WRITE_WIIU=1` | emit a raw big-endian v148 Wii U zone |
| `OAT_REWRITE=1`    | write the loaded zone back out |
| `OAT_IGNORE_SIG=1` | make the signature step non-fatal |
| `OAT_WIIU_BLOCKREMAP=1` | read genuine Wii U fastfiles via the console read path (console struct layouts + block remap) |
| `OAT_ALIAS_NULL=1` | resolve unresolvable console references (reused-memory / cross-zone / empty DELAY block) to null / a zeroed buffer so the read continues; lossy (read-only aid, not a faithful relink) |
| `OAT_RT_PHYS=c60000` | reserve the `RUNTIME_PHYSICAL` block (hex) |
| `OAT_DROP_GSC=1`   | omit `scriptparsetree` assets |
| `OAT_STRIP_GSC=1`  | stub `scriptparsetree` assets to empty |
| `OAT_GSC_DIR=<dir>`| substitute scripts by name from a folder |
| `OAT_DUMP_ZONE=<f>`| dump the decompressed content to `<f>` |

> Unlinker name-verifies a fastfile against its internal name, so the app stages a copy
> named to match before invoking it. Keep some free disk space next to the source.

---

## Building a standalone EXE

`build.bat` uses **PyInstaller** to produce a single-file `WiiU_FF_Studio.exe`:

```
build.bat
```

It will `pip install pyinstaller` if needed, bundle `wiiu_ff.py`, `salsa20.py` and
`zone_validate.py`, and drop the EXE in `dist\`. Ship `dist\WiiU_FF_Studio.exe`
together with `README.md`, `USAGE.md` and (if you want the OAT tabs to work out of the
box) an `oat\Unlinker.exe` folder next to it.
