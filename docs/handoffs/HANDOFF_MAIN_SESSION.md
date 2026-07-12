# HANDOFF — MAIN SESSION (central coordinator)

You are taking over as the **main session**: the central reasoning ground that coordinates multiple
parallel worker sessions toward the final goal. You do not usually write the code yourself — you
route work, write handoffs, verify claims, catch cross-session collisions, correct course, and keep
the documentation truthful. This doc is your operating manual + current board state.

## The goal
Convert a **PC (Plutonium/T6) Black Ops II map fastfile** into a **bootable Wii U (v148) .ff + .ipak
fully from PC source** — no genuine console backbone ("no-backbone"). Target: **mp_skate** (PC-only
DLC map, never shipped on Wii U). Zombies maps are the tier after MP.

## Read these first (in order)
1. `PROJECT_STATE.md` — master component-status index + critical path (keep it updated; it's the
   START-HERE doc, pointed to from memory MEMORY.md).
2. `CAVEATS_nobackbone_boot.md` — every deliberate approximation + how to interpret the first boot.
3. The active per-session handoffs (below).
Memory: the auto-memory index MEMORY.md points here; per-track memories exist for every area.

---

## THE BOARD — active worker sessions (as of 2026-07-09)

### 1. ASSEMBLE session (critical path) — `HANDOFF_xmodel_close_and_assemble.md`
- **State:** XModel fully closed (mp_skate 466/466 incl. 7 emit-rigid skinned; raid 440/440). The
  assemble loop (`produce_nobackbone.py::assemble_zone`) RUNS: 27.3 MB / 495 assets emitted, and it
  **names every remaining gap with counts**: techsets ×245 (wiring only — Track B corpus/manifest
  exist), FX ×79 (header done, elems layout-identical), SndBank ×1 (49.8 MB — likely a **byte-copy**,
  PC↔WiiU byte-identical, try that before treating as RE), XAnim ×7 + smalls, GfxWorld ×1 (Track F).
- **Approved plan:** techset wiring → FX → SndBank byte-copy → XAnim+smalls → GfxWorld stub →
  raid-oracle control → container+pack → first boot.
- **KEY RISK you must gate:** omap `interior_approx=2613`. Self-consistency validates SIZES not
  POINTER VALUES — a wrong interior target is a silent dangling pointer. **The raid-oracle control
  (diff assembled raid vs genuine, with a known-exception allowlist: material hashIndex ×9,
  substituted techsets, −16/−32 class, skinned) is the detector. Do NOT let mp_skate boot before the
  raid control passes with only allowlisted diffs.** `unresolved=1178` must go to 0 (then fatal).
- **MUST PICK UP:** the WEAPON session edited shared files (`pc_walk.py`, `walker.py`,
  `struct_layout.py`, `material_convert.py`, `clipmap_pc.py`) — the assemble session must pull these
  before its next run; one editor at a time on those files.

### 2. TRACK F session (critical path) — `HANDOFF_trackF_nobackbone.md`
- **State:** frontier quantified: ~7.2 MB GX2 textures (existing image pipeline; **cubemaps verified
  6/6 byte-exact**), ~4.2 MB PC-sourced bounded conversions (smodelDrawInsts 3.69 MB = GfxPlacement
  52→28 packing + lmapVertexInfo 12→32×4; materialMemory; cells), **~90 KB true novel synthesis**
  (streamInfo / sortedSurfIndex reorder / smodelCastsShadow — validate vs raid oracle).
- **Interface rule:** Track F owns `gfxworld_*.py` (produces the console GfxWorld regions); the
  assemble session owns `produce_nobackbone.py` (calls it). Stubs acceptable for the first artifact —
  smodelDrawInsts stub renders base world without props (geometry lives in surfaces/vd0).

### 3. WEAPON session — **span bar DONE 2026-07-09** (`HANDOFF_weapon_consumer.md` banner)
- ALL five zones now walk end-to-end: raid 887, skate 840, nuketown 840, zm_nuked 3158,
  zm_transit 3254. Done by fixing the GENERIC walker (6 shared bugs), not a bespoke consumer.
- **Remaining = the CONVERT bar** (PC→console weapon bodies vs the zm matched-pair oracle) —
  **zombies-tier, not on the mp_skate path** (skate has 0 inline weapons). Recommendation given:
  park it unless zombies capacity is wanted.

### 4. DLC session — `HANDOFF_dlc_infra_convert.md` (fact-first doc; UPDATE 2026-07-09 section)
- **State:** native load-zone converter (`assemble_loadzone.py`) validated **byte-identical** vs the
  genuine console `dlc0_load_mp` oracle (one safe header word off); dlc1–4_load_mp converted (in
  `dlc loading\native\`), NOT yet Cemu-tested. zm zones deliberately not emitted (SndBank sab
  checksum + hash gaps, documented). All 14 DLC ipaks whole-converted (BE-valid readback).
- **Directed next step:** **Cemu-test the byte-identical `dlc0_load_mp.ff` FIRST** — it resolves the
  open fork from the earlier `Sys_Error` (was the crash conversion or pack/deploy? byte-identical
  input isolates it). Then loadscreen image-header wiring, then zm.
- Hardware facts already established: AOC title mount rules (`content\0010\`, complete folder title
  with code/app.xml), engine requests `dlc0_load_zm.ff` (not dlczm0), DLC-gate RPL patch surfaces
  DLC0+DLC1 (mapsTable only has rows for those), zombies menu tolerates missing load zones (-6).

## Held / deferred (do NOT start without cause)
- **Skinned skin-stream synthesis** — zombies tier; emit-rigid is PERMANENT for mp_skate (the 7 are
  ambient props + the dog). `HANDOFF_skinned_skinstream.md` (Step 1 = OAT_NO_SKIN loader test).
- **Lighting repack** (tangent + vd1-V "runs darker") — post-boot polish, bounded RE.
- **Menu registration / mapsTable** — gated on the DLC session's Cemu test outcome.
- **Repo migration** ("frankenstein → real repo") — breaks live sessions' import paths; only when
  sessions settle. A shareable snapshot already exists: `WiiU_T6_Toolkit/` (code+docs, no game data,
  honest per-tool state in its README; license question answered: GPL-3.0, OAT is GPLv3).

---

## CRITICAL PATH to the first mp_skate boot (the thing everything serves)
```
[assemble session] techsets ×245 → FX ×79 → SndBank byte-copy → XAnim+smalls
[track F]          smodelDrawInsts (or stub) + GX2 routing + ~90 KB synthesis (or stubs)
        ↓
raid-oracle control (allowlist) — THE GATE; validates omap pointers    ← do not skip
        ↓
container + pack + sig-patch → mp_skate_wiiu.ff → Cemu (first-boot = diagnostic, not finish)
```
First boot expectation: interpret against `CAVEATS_nobackbone_boot.md` §"How to read the first boot".
Cemu does NOT capture OSReport → failures give a symbolized stack (`rpl_symbolize.py`), no message.

## Beyond first boot (tiers, in order)
1. **Playable MP:** lighting repack · menu/mapsTable registration · collision completeness · sound.
2. **Zombies:** WEAPON convert bar · skinned synthesis (or rigid+test) · ZM asset-list inserts
   (GLASSES/LEADERBOARD/LOCALIZE/XGLOBALS) · ZM load-zone SndBank gaps.

---

## HOW TO DO THIS JOB (the operating principles that made it work)
1. **Verify, don't trust — including your own prior claims.** Multiple "known facts" were wrong until
   measured (Material 112→104, XSurface 64→128, "mp_skate aliases models" → 466 inline, "0 skinned"
   → 7, "DPVS sizing" → skyBoxModel). When a session reports, spot-check the load-bearing claim if
   cheap. Own your errors explicitly — the record matters more than looking right.
2. **Raid-luck-masking is the house pattern.** Raid is repeatedly the degenerate case that hides bugs
   (alignment, aliased fields, absent types, insert rules). NEVER accept a rule validated only on
   raid for a blind build — demand ≥2 console-oracle maps.
3. **OAT-load-order diff** is the standard drift-killer: diff a probe/dispatcher against the generated
   `*_t6_load_db.cpp` (authoritative serialization order). No rebuild needed. OAT itself NEVER made a
   bootable ff — per-struct byte oracle only (clarity tag in `HANDOFF_native_converters.md`).
4. **Two bars, never conflate:** byte-exact-vs-oracle (for converters with a genuine counterpart) vs
   **self-consistency = loadability** (for no-backbone output; re-walk consumes exactly the emitted
   length). Genuine byte-parity is IMPOSSIBLE for no-backbone by design — don't let a session chase it.
   BUT: self-consistency does not validate pointer VALUES — that's what the raid-oracle control is for.
5. **Chase to root.** The visible drift is usually downstream of the real bug (destructible→
   PhysConstraints, XAnim@801→WEAPON@788, "767 techset variant"→2-byte upstream). The strong per-type
   resync + trace-back finds it; weak next-word checks mask cascades.
6. **Stub-and-test before synthesizing.** Valid-shaped stubs (count=0, flag-cleared rigid) turn "is
   this region required?" into a cheap boot test. The walking-skeleton discipline: reach the
   end-to-end artifact fast; each failure NAMES the next constraint.
7. **Scope worker sessions tightly.** Standalone handoffs with: current state, pinned facts,
   do/don't, validation gate, file ownership, "done when". File-collision rule: ONE editor per shared
   file (`pc_walk.py` is the hot one). When two sessions meet, define the interface boundary
   explicitly (Track F: `gfxworld_*.py` vs assemble: `produce_nobackbone.py`).
8. **Keep the docs truthful in real time.** Update `PROJECT_STATE.md`, the caveats register, and the
   memory index as milestones land; kill stale claims aggressively (they cost sessions real time —
   the wrong vd0 handoff nearly sent a session down a multi-day PPC rabbit hole).
9. **Constraints:** NEVER write under `E:\` (installed game; copy out first — ff_decrypt writes next
   to input). struct_layout is WRONG for GfxWorld draw-onward + several console sizes — trust probes
   + empirical pins. Cemu runs the installed RPL (runtime = file + 0x2000).

## Decision heuristics the user relies on you for
- **"What should run in parallel?"** — keep the critical path (assemble + Track F) staffed first;
  zombies/DLC tiers are parallel-if-capacity; hold polish until after boot.
- **"Is X the last blocker?"** — almost never; enumerate the tier list honestly (boot → playable →
  zombies) rather than saying yes.
- **"Should we do the deeper/purer fix?"** — usually no until the boot proves it's needed
  (substitution over shader recompilation; stub over synthesis; byte-copy over converter).
- When a session asks "continue or checkpoint?" — push through if the remaining piece is bounded
  and oracle-backed; checkpoint when the next piece is a genuinely new sub-project.

## The user
Runs multiple Claude sessions in parallel and relays their status reports to you. Expects: direct
answers, honest correction of your own past errors, concrete next instructions per session, and
handoff docs they can paste to workers. They test on Cemu themselves (hardware results come back
through them). Standing security constraint: never modify files under `E:\...` installs.
