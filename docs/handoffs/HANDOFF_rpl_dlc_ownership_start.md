# HANDOFF — RPL: patch the START-path DLC ownership check (unlock all 4 DLC)

2026-07-10. RE + patch task on the game RPL. Goal: DLC maps are **startable** (Start Match not
greyed), for all four map packs. Standalone; independent of the assemble/DLC-relink sessions.

## The problem (evidence-grounded, from the Cemu log this session)
- The frontend boots; the RPL DLC-gate patch surfaces DLC1 + Nuketown rows in the menu.
- Selecting them → **Start Match is greyed.** Adding the converted `_load_mp.ff` zones changed
  nothing (correct — those are mount/loadscreen zones, orthogonal to ownership).
- **Root cause in the log:** `nn_aoc.AOC_Initialize` logs as **"Unsupported lib call"** —
  Cemu stubs the Add-On Content library. Only ONE nn_aoc call in the whole session; it fails,
  so the game's AOC subsystem never enumerates owned DLC → the start-path ownership check
  concludes "not owned" → Start greyed. Both DLC1 AND Nuketown greyed = the common factor is
  entitlement-gated content, the fingerprint of an ownership gate (not a mapsTable/menu-line
  or load-zone problem).

## What already exists (build on it, don't redo)
- **Listing gate, already patched:** `Content_PlayerHasDLCForMapPackIndex` @0x0241CBA0 →
  `li r3,1; blr`, located by symbol via `wiiu_ref/rpl_dlcgate_patch.py`. This forces the
  menu to SHOW DLC0+DLC1 rows. It is NOT enough for Start — a different check gates that.
- Tooling: `wiiu_ref/rpl_dlcgate_patch.py` (symbol-located patch — mirror/extend it),
  `wiiu_ref/rpl_sigpatch.py` (RPL section reader + patched-RPL writer), `capstone` installed.
- Patched RPL deploys to the **update partition**:
  `…\AppData\Roaming\Cemu\mlc01\usr\title\0005000e\1010cf00` (WRITABLE — under AppData).
  **The base game is at `E:\Wii U Black ops 2` — NEVER write there.** Patch the AppData copy.

## The task
1. **Find the start-path ownership check(s).** Method: dump the RPL symbol table
   (`rpl_sigpatch.py` section reader) and grep for DLC/AOC/entitlement/availability bool
   functions — candidates: `Live_*DLC*`, `Content_*` (siblings of the @0x0241CBA0 function),
   `*HasDLC*`, `*IsDlcAvailable*`, `*Owned*`, party/lobby map-validation. Also trace the
   `nn_aoc.AOC_Initialize` import's referencing callers (where its failure propagates into a
   global "DLC available" flag). Disassemble around each (capstone) to confirm which one
   returns the bool the Start button's enable-state reads.
2. **Confirm before patching** which function actually drives the greyout — the button state
   is a UI query result; patch the function whose return flips it, not the first plausible
   symbol. If cheap, patch one candidate at a time and re-check the log/UI (the greyout is the
   oracle).
3. **Patch to force owned/available, index-agnostic** (force TRUE for ANY map-pack index, so
   all 4 DLC pass, not just DLC1) — `li r3,1; blr` style, same as the listing gate. If the
   check reads an owned-mask/array, force the mask full rather than a per-index return.
4. **Deploy** the patched RPL to the AppData update partition; keep a backup of the original.

## Coupled prerequisite for "all 4" to be VISIBLE (flag, don't necessarily fix here)
The Wii U `mapsTable` has rows for **DLC0+DLC1 only**; DLC2/3/4 maps do not appear even with
the gate open (confirmed). So even after this ownership patch, DLC2/3/4 won't SHOW until their
mapsTable rows are added — that's the **patch_mp/patch_zm relink** job (separate session). This
handoff makes owned-content STARTABLE; the relink makes DLC2-4 APPEAR. "All 4 DLC startable"
needs both. Validate this patch on DLC1+Nuketown (already visible) now; DLC2-4 confirm after
the relink lands.

## Validation (Cemu, via user)
- DLC1 + Nuketown: Start Match **no longer greyed**; selecting → launches (or at least attempts
  the map load — capture what zone it requests).
- Log check: the patched function returns owned; no new AOC-dependent call re-greys it. The
  user launches; read `…\Cemu\log.txt` (Cemu rotates it per launch — the whole file is the
  session). Grep for the patched symbol, `nn_aoc`, and any `Sys_Error`/fault.

## Constraints
Never write under `E:\` (base game). Patched RPL → AppData update partition only, with a
backup. Verify-don't-trust: confirm the greyout-driving function empirically (it's the oracle)
before locking in the patch. Record the found symbol + offset + patch bytes in
`FINDINGS_rpl_dlc_ownership.md` and update memory `wiiu-map-menu-registry`.

## Definition of done
The start-path ownership check is located (symbol + offset recorded), patched index-agnostic,
deployed to the AppData update RPL; on Cemu, DLC1 + Nuketown are startable (Start un-greyed,
map-load attempted); the mapsTable-row dependency for DLC2-4 visibility is documented for the
relink session. Findings + memory updated.
