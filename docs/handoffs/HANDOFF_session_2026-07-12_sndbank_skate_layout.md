# HANDOFF — 2026-07-12 session: field-aware SndBank + skate measured-tail-anchor layout fix

This is the MAIN-SESSION record. It supersedes nothing but continues
`HANDOFF_session_2026-07-12_layout_breakthrough.md`. Read that first for the earlier
same-day work (GfxWorld crash = layout; first skate measure→rebake). This doc covers
everything after: the field-aware SndBank converter, the whole raid gameplay-crash
investigation (which resolved to a test artifact), the console sound-hash RE dead-end,
and the skate layout breakthrough that cleared TWO crash layers.

═══════════════════════════════════════════════════════════════════════════════
## TL;DR — where we stand
═══════════════════════════════════════════════════════════════════════════════
1. **Field-aware SndBank converter — DONE + BOOT-PROVEN.** Replaced the blanket _swapw
   (which corrupted SndAlias sub-u32 fields + Radverb/Duck name[32]) with per-struct
   field-aware endian. Cleared the raid `+0x3817ce` AX-voice crash (isolation build boots,
   audio inits, 1222 frames). This is the session's solid deliverable.
2. **Raid gameplay wild-read (0xe61434b5) = BISECT ARTIFACT, not a bug.** Proven: 100%-genuine
   ALL3 runs clean; the wild-read is invariant to every SndBank content/.sab/checksum change;
   the .sab is never even opened. Our bank's SIZE ≠ genuine shifts downstream GENUINE bodies
   under GEN_POLICY → wild ptr. CANNOT occur in self-consistent from-scratch skate. Raid is
   fully explained; nothing more to fix there.
3. **Console sound name-hash = CUSTOM, uncrackable without disasm.** fnv/murmur/jenkins/djb2/
   crc all fail; additive-poly disproven (final avalanche mix). SndAlias.name = per-build
   string-pool ptr-id (not a content hash). Only matters for genuine-.sab maps (raid); skate's
   .sab is self-consistent so it doesn't need it.
4. **★ SKATE: cleared TWO crash layers via the measured-tail-anchor method.**
   - audio-endian `+0x3817ce` → field-aware SndBank ✅
   - tail-layout `+0x20a436`/`+0x20b6aa` → measured 35-anchor piecewise GfxWorld-tail map ✅
   - now at a **material-registration NULL-deref** (guest [null+0x10]) — localized, both static
     hypotheses ruled out → see the FRESH-SESSION handoff `HANDOFF_skate_material_nullderef.md`.

═══════════════════════════════════════════════════════════════════════════════
## 1. Field-aware SndBank converter (native_linker/smalls_convert.py)
═══════════════════════════════════════════════════════════════════════════════
`convert_sndbank` rewritten alias/radverb/duck emit (from T6_Assets.h: SndAlias@6328,
SndRadverb@3115, SndDuck@3139, SndAliasList@3100):
- `_alias_be(p100)`: swap32 [0:52] (6 ptr/u32 + 8B flags + 5 u32) · swap16 [52:86]
  (17 u16/i16 fluxTime..dopplerScale) · verbatim [86:96] (10 u8) · ZERO pad [96:100].
- `_radverb_be`/`_duck_be`: char name[32] VERBATIM + swap32 tail.
- aliasIndex: swap16 (SndIndexEntry{u16,u16}, was swap32).
VALIDATION: converted raid bank re-walks BYTE-EXACT with genuine BE probe (sndbank_probe.
parse_sndbank): name='mpl_raid.all', 2656 lists, 12467 aliases, lands EXACTLY on next asset.
Size-preserving (verified) → skate's measured_rtmap stayed valid. Scripts: _derive_sndalias.py,
_verify_fieldmap.py, _validate2.py.
OPT-IN ORACLES added (default None, general path unchanged) — only for genuine-reference maps:
`SNDBANK_ALIAS_ORACLE` (per-alias name@+0/assetId@+16, positional; SKIP FOLLOW names or the
walk desyncs), `SNDBANK_ALIASINDEX_ORACLE`, `SNDBANK_LOADEDASSETS_ORACLE` (entryCount/dataSize),
`SNDBANK_HEAD_OVERLAY` (checksum blocks). Driver: _build_raid_oracle.py.

═══════════════════════════════════════════════════════════════════════════════
## 2. Raid gameplay-crash investigation → BISECT ARTIFACT (fully closed)
═══════════════════════════════════════════════════════════════════════════════
Chain of builds (all deployed to 0005000e/…/english/mp_raid.ff):
- `mp_raid_bisect_sndmain.ff` (genuine all + genuine english + our field-aware bank) → BOOTS,
  audio, 1222 frames, then guest-JIT wild read guest 0xe61434b5 (dump 29252). → +0x3817ce CLEARED.
- assetId oracle (genuine name/assetId/aliasIndex, order proven by 0/2656 list-id match) → 2414
  frames (2× longer), SAME 0xe61434b5. Doubled runtime = assetId mismatch was real, but not sole.
- +genuine loadedAssets (ec 654/ds 11519896, was 652/12269568 — 749KB too big) + genuine checksum
  → "sound bank failed to load mpl_raid.all. build problem" (engine REJECTS bank; the .sab is
  never opened → in-memory validation). Bisected: CHECKSUM overlay is the "build problem" trigger.
- Matched pair (our bank + our CONVERTED .sab via sab_convert of E:/pluto_t6_full_game raid .sab,
  deployed to update-partition sound/) → SAME 0xe61434b5.
- **ALL3 (100% genuine bodies + genuine .sab) → runs 2074 frames CLEAN, no 0xe61434b5.**
CONCLUSION: 0xe61434b5 is invariant to every SndBank change, .sab never opened, ALL3 clean ⇒ our
bank's SIZE ≠ genuine shifts downstream GENUINE bodies under GEN_POLICY (mirrors genuine layout) →
their runtime ptrs land wild. A BISECT-HARNESS ARTIFACT. Not a converter bug; impossible in
from-scratch skate. The raid bisect validates CONTENT (loads, +0x3817ce, matched .sab) but NOT
gameplay layout. `_bisect.py` gained `~Root` (all-except) + auto-pack. Genuine E: .sab restored.

═══════════════════════════════════════════════════════════════════════════════
## 3. SKATE — measured-tail-anchor layout method (the breakthrough)
═══════════════════════════════════════════════════════════════════════════════
PROBLEM: loader_sim CANNOT walk past GfxWorld — its span is 59.7M→99.85M (40MB blob); SndBank +
clipMap + the whole audio tail are lumped in, never individually placed → the rebake EXTRAPOLATES
them. The tail is also not needle-measurable (pointer-heavy assets relocate at runtime; loadedAssets
data zeroed) → widening _measure_real.py's window HURT (51%→37%).

INSIGHT: measure the tail via STABLE STRINGS (immune to relocation). The SndBank name 'mpl_skate.all'/
'.english' → measured runtime pos vs zone stream pos = the real gfx_skip expansion.
- _measure_sndpos.py: SndBank landed at delta +1,081,088 (both names). But the rebake's rtmap carried
  GfxWorld's start-delta +1,252,389 forward → placed SndBank +1,275,612 = **194,524 B too late** →
  DB-linker relocates the mis-placed pointer-array → +0x20a436/+0x20b6aa.
- _measure_tail.py mapped the FULL divergence curve (ascii-needle unique search across the tail):
  PIECEWISE — +1,252,389 (GfxWorld start) holds to ~76.3M, DROPS −173,378 → +1,079,067 at ~77.1M
  (inside GfxWorld body), rises +2,021 → +1,081,088 at ~82.8M (SndBank onward). Single anchor missed
  the 77.1M/82.8M transitions.
- _apply_tail_anchors.py: measures 35 unique tail points from a dump, adds them ALL as SNDANCHOR spans
  in _skate_simmap.pkl + realmap entries → MeasuredRuntimeMap.rt() piecewise-accurate.
- Rebake (_rebake_skate.py) → deploy → **host relocation crashes GONE** (0 host exceptions, 760 frames).
KEY LESSON: the loader's block-5 LAYOUT is fixed by zone STRUCTURE (sizes/FOLLOW), NOT our baked ptr
VALUES → measured runtime positions are STABLE ground truth across rebakes (SndBank +1,081,088 in both
dumps 19388 & 39080). Our baked values chase the layout, so the crash moves per-rebake while layout stays.
The measure→rebake tunable is ANCHOR DENSITY over the un-walkable GfxWorld tail — NOT coverage%.
REPEATABLE LOOP: boot → dump → `python _apply_tail_anchors.py <dump>` → `python _rebake_skate.py` →
deploy → boot. (Skate dumps rotate out of C:\CemuFullDumps fast; re-boot to regenerate.)

CURRENT SKATE STATE: after the 35-anchor rebake, skate boots 760 frames then a guest-JIT NULL+0x10
deref (dump 40004) in MATERIAL/TECHSET registration. Localized; both static hypotheses ruled out.
FULL detail + next steps → `HANDOFF_skate_material_nullderef.md`.

═══════════════════════════════════════════════════════════════════════════════
## 4. DEPLOY PATHS / BUILD ARTIFACTS / TOOLS
═══════════════════════════════════════════════════════════════════════════════
Deploy: skate = mlc01/usr/title/0005000c/1010cf00/content/0010/english/mp_skate.ff ;
        raid  = mlc01/usr/title/0005000e/1010cf00/content/english/mp_raid.ff (mlc01 =
        C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\mlc01). NEVER write E:\ (base game).
Build: `python _rebake_skate.py` (skate, uses measured_rtmap) ; `python _build_raid_oracle.py [mode]`
        (raid oracle: neither/loaded/checksum/both) ; `python _bisect.py ALL|NONE|~SndBank|Root,...`.
        Pack = WiiU_FF_Studio/wiiu_ff.pack(zone,'mp_skate'|'mp_raid'). USE `python` not `python3`.
Current deployed: skate = 35-anchor rebake (mp_skate_measured.ff); raid = ALL3 (mp_raid_bisect_ALL3.ff)
        + genuine E: .sab (converted-.sab override removed).
Dumps: WER full dumps in C:\CemuFullDumps\Cemu.exe.<pid>.dmp (Memory64List stream 9; guest base from
        Cemu log "Init Wii U memory space (base: …)", per-run ASLR). Use Cemu log rip, NOT WER
        ExceptionStream (first-chance red herring). Scripts parse dump + capstone-disasm the JIT.
Scratch scripts kept (native_linker/): _derive_sndalias, _verify_fieldmap, _validate2 (SndBank
        validation); _bisect, _bisect_sndmain, _build_raid_oracle (raid builds); _rebake_skate,
        _measure_sndpos, _measure_tail, _apply_tail_anchors (skate layout); _crack_sndhash/_crack2/
        _crack_assetid/_solve_poly (hash RE dead-end); _trace_null (null-deref); _measure_skate_audio,
        _validate_skate_sab, _dump_skate34096. Removed: 4 per-dump analyzers (_dump29252/38080/15904/35852).

═══════════════════════════════════════════════════════════════════════════════
## 5. OPEN WORK (priority order)
═══════════════════════════════════════════════════════════════════════════════
1. **SKATE material-registration NULL-deref** — the current blocker. See
   `HANDOFF_skate_material_nullderef.md`. This is the critical path to a skate boot.
2. Skate: the layout method may need re-anchoring after any content change (re-run the loop).
3. (Optional) Raid full playable = needs our-bank + our-.sab matched pair BUT the bank must be
   genuine-SIZED to not shift genuine bodies — only meaningful as an end-to-end pipeline demo, not
   required (raid is a control map; skate is the deliverable).

Memory updated: gfxworld-crash-is-layout-not-content.md, xmodel-inline-image-transplant.md, MEMORY.md.
