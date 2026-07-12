# HANDOFF — ASSEMBLE: container authoring → pack → mp_skate boot artifact #1

GATE PASS is declared (2026-07-10, ADDENDUM 10): raid unresolved 0, skate blind unresolved 0
fatal-green with blind constants, anchors ALL PASS. The linker is ready. This handoff is the
LAST assemble stage: author the real container, pack, and hand the user a Cemu-bootable
mp_skate artifact. Most of this is already-validated machinery — this is assembly of proven
parts, not research.

## The work
1. **Container authoring** — feed the real base into `our_arr`:
   - Asset array via `_assetlist_author.py` (type remap byte-exact 886/886 + 799/799; MP
     insert set as corrected: **aliased MAP_ENTS row @idx1** (raw 48; no body) + the extra
     FOLLOW SOUND row = **`mpl_skate.english`** (already authored via `author_english_bank`,
     parses end-exact — wire it as the SOUND list row).
   - String table: reuse PC verbatim (proven identical).
   - Per-asset headerPtr (FOLLOW/alias through the live omap) + header block sizes computed
     from the emission (block-5 virtual total from the sim; block-2 physical incl. the
     SndBank zeroed-buffer arithmetic already baked).
2. **Offline verification (before any pack):**
   - Full-zone re-walk of the authored container (`wiiu_zone` + the console-side walker):
     consumes exactly the emitted length, EOF-exact, all self-checks green.
   - Run the whole guard suite one final time: anchors ALL PASS, both oracle gates, ST, 
     alloc_events. NOTHING ships with a red guard.
   - **Raid dry-run first**: author + pack the assembled RAID container and re-walk it — 
     raid has a genuine container to diff against (header words, block sizes, asset array 
     bytes). Any container-level diff outside known classes gets explained before skate packs.
3. **Pack** — `WiiU_FF_Studio/wiiu_ff.py`, genuine 0x7FC0 blocks, v148 BE; zero-sig +
   `rpl_sigpatch.py` deployment path (user's Cemu already runs patched RPLs).
4. **Ipak** — author the mp_skate .ipak from PC sources (base+mp+dlc1 auto-select) if the
   user hasn't pre-built it; byte-exact machinery. The ts-dangle mirror targets and streamed
   image refs make the ipak REQUIRED at boot — ship .ff + .ipak together.
5. **Deliverable to the user**: `mp_skate_wiiu.ff` + ipak + a one-page boot sheet:
   where to place both files, which zone name the engine will request (coordinate with the
   DLC session's patch_mp findings if available — otherwise console/exec launch), and what
   to capture on failure (crashlog for `rpl_symbolize.py`).

## How to read boot #1 (set expectations in the boot sheet)
Boot #1 is a DIAGNOSTIC. Interpret against `CAVEATS_nobackbone_boot.md` — every deliberate
approximation is registered: the named blind paths (techset hook fires once —
hdr_create_lut2dv_827z0f8q; ts-dangle mirrors; KD streamInfo synthesis; PC-order
sortedSurfIndex; BC3 lightmap reencode; SndBank PC-order head = no working sound expected;
emit-rigid skinned ×7). Cemu gives no OSReport: failure = symbolized stack via
`rpl_symbolize.py` (installed RPL, runtime = file + 0x2000). Success bar for artifact #1 is
LOAD + any render — not correctness of everything registered.

## Constraints (final reminder)
Never write under `E:\`. One editor: you own the assemble/converter/gfxworld files. Keep
PROJECT_STATE truthful — when the artifact ships, update it to "artifact #1 delivered,
awaiting boot result" rather than claiming a boot.

## Definition of done
Raid container dry-run explained-clean; skate container authored, re-walk EOF-exact, all
guards green; packed + sig-path-ready `mp_skate_wiiu.ff` + `.ipak` delivered with the boot
sheet. The user boots it. Whatever happens next is the first-boot debugging tier — a new
handoff from its evidence.
