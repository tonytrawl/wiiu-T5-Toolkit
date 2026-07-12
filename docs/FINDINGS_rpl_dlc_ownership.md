# FINDINGS — RPL start-path DLC ownership check (unlock DLC startable)

2026-07-10. Resolves HANDOFF_rpl_dlc_ownership_start.md. Target: `t6mp_cafef_rpl.rpl`
(MP engine RPL) on the AppData update partition. Base game at `E:\` never touched.

## Root cause (static RE, matches the Cemu-log AOC symptom)
The map-select "can we start this map" query is the LUI Lua binding
`__LUI_CoD_LuaCall_DoesPartyHaveDLCForMap` @ **0x028c74d0**. It does:

```
mapBits = Live_GetMapSource(mapIndex)            # 0x023c4cec : per-map DLC source bits (base=2)
ownMask = Live_CurrentFullPartyMapPackFlags(pty) # 0x02152e78 : packs owned+enabled, AND'd over party
return (ownMask & mapBits) != 0                   # `and.` at 0x028c7574 / 0x028c75a8
```

Both the in-party/public-online branch and the solo/local branch funnel through
`Live_CurrentFullPartyMapPackFlags`. That mask is built from
`Content_GetEnabledContentPacks` (0x02433f68) AND-reduced across party members.
`nn_aoc.AOC_Initialize` is a **stubbed** import on Cemu ("Unsupported lib call"),
so the AOC subsystem never enumerates owned DLC → the enabled/owned mask carries no
DLC bits → `ownMask & mapBits == 0` → `DoesPartyHaveDLCForMap` returns false →
**Start greyed.** This is a different gate from the LISTING gate
`Content_PlayerHasDLCForMapPackIndex` @0x02435850 (already patched → `li r3,1; blr`),
which only governs whether rows SHOW.

## Patch applied (index-agnostic — force the OWNED MASK full)
Per handoff steer "force the mask full rather than a per-index return":

- **Symbol:** `Live_CurrentFullPartyMapPackFlags__FP11PartyData_s`
- **VA:** 0x02152e78 (entry)
- **Orig bytes:** `mflr r0; stwu r1,-0x10(r1)` (7C 08 02 A6 / 94 21 FF F0)
- **Patch bytes:** `li r3,-1; blr` = **0x3860FFFF 0x4E800020** → returns ownMask=0xFFFFFFFF
- Safe: returns before prologue allocates a frame (r1/LR untouched).

Every map's `Live_GetMapSource` bits then AND non-zero → `DoesPartyHaveDLCForMap`
true for ALL map-pack indices, both branches. One patch, all 4 packs, index-agnostic.

Tool: `wiiu_ref/rpl_ownership_patch.py` (symbol-located; mirrors rpl_dlcgate_patch's
section/CRC machinery; `patch_rpl()` is parametrized on symbol + 2 instruction words).

## Deploy
- In/out: `…\Cemu\mlc01\usr\title\0005000e\1010cf00\code\t6mp_cafef_rpl.rpl`
  (patched IN PLACE on the copy that already had the dlcgate + contentpack patches;
  size unchanged 8014669 B, pure text-section overwrite + CRC fix).
- Backup: `t6mp_cafef_rpl.rpl.preownership.bak`.
- Verified in the written file: BOTH gates live —
  `Content_PlayerHasDLCForMapPackIndex @0x2435850 = li r3,1; blr` (listing) and
  `Live_CurrentFullPartyMapPackFlags @0x2152e78 = li r3,-1; blr` (start/ownership).

## Validation (needs a Cemu run by the user — UI is the oracle)
1. Launch; open the MP map/private-match select. DLC1 + Nuketown rows visible (listing gate).
2. Select DLC1 / Nuketown → **Start Match should no longer be greyed**; selecting should
   attempt the map load (capture which zone it requests).
3. Log check (`…\Cemu\log.txt`, rotates per launch): no new AOC-dependent call re-greys;
   grep `nn_aoc`, `MapPackFlags`, and any `Sys_Error`/fault.

## Fallback if Start is still greyed
If some other consumer drives the greyout, the direct per-map Lua binding is the next
patch target: `__LUI_CoD_LuaCall_DoesPartyHaveDLCForMap` @0x028c74d0 — force it to push
Lua `true` unconditionally. (Prefer the mask patch above; it's the root cause and covers
more consumers — `Party_*MissingMapPack*`, playlist DLC checks, etc. all read the mask.)

## STAGE 2 (2026-07-11): mask patch un-greyed Start, but Select → popup
After the mask patch, Start Match un-greyed (confirmed on Cemu) but selecting the map
raised the popup **"You do not have this map or the content is damaged … download map
packs from the Nintendo eShop."** — localizedstring key `MPUI_PLAYER_DOESNT_HAVE_MAP_PACK`
(@0x1006eda5 in the RPL; sibling `CONTENT_NOT_OWNED` @0x1010f074). The key is reached
via Lua, not a direct .text lis/addi, so the gating decision is a LuaCall bool.

Remaining ownership funnel: `Content_PlayerHasDLCForMap` @0x024358dc iterates the
**content-pack→map name table** (stride 0x70, name@+0x20, packIdx@+0xdc → PackIndex) and
returns 0 when the selected map's name isn't in that table — a DIFFERENT structure from the
owned-mask. `IsMapValid` @0x028c99d8 funnels through it (returns false when it's 0).
Third patch applied (index-agnostic):
- **Symbol:** `Content_PlayerHasDLCForMap__FPCc` @ **0x024358dc**
- `mflr r0; stwu…` → **`li r3,1; blr`** (0x38600001 0x4E800020)
Deployed in place; backup `t6mp_cafef_rpl.rpl.prehasmap.bak`. All THREE gates verified live:
PackIndex `li r3,1`, MapPackFlags `li r3,-1`, PlayerHasDLCForMap `li r3,1`.

**Interpretation of the popup wording** — it is "not owned OR content damaged." The three
patches close the *ownership* side completely. If the popup persists after these, the live
branch is the *content-damaged/missing* side = the DLC map's actual .ff/ipak zone content is
not ported (the separate content-port job), NOT an ownership gate. Forcing PlayerHasDLCForMap
true also advances past the pre-flight check to the real map-load, so the next Cemu run should
either launch or fault on a specific missing zone — capture which zone it requests.

## STAGE 3 (2026-07-11): popup is NOT an ownership boolean — it's launch/content
Isolation test (user): in the LOCAL/custom-games flow, **base MP maps launch fine**; only
**DLC1 (Revolution) MP maps** raise the popup. So it's DLC-specific, not a broken flow.

Exhaustively verified EVERY DLC ownership signal to the UI is now forced owned:
- Content_PlayerHasDLCForMapPackIndex @0x2435850 = li r3,1
- Live_CurrentFullPartyMapPackFlags   @0x2152e78 = li r3,-1
- Content_PlayerHasDLCForMap          @0x24358dc = li r3,1
- IsContentAvailableByPakName (LuaCall)@0x28e6238 = li r3,1 (already, from contentpack patch)
- GetMaps (custom-games list) @0x28c934c tags each map via the (forced) PackIndex → owned
- DoesPartyHaveDLCForMap @0x28c74d0 → true (mask forced); IsMapValid @0x28c99d8 → true
  (funnels PlayerHasDLCForMap); HasDLCContent @0x28c9450 → true (PackIndex).

Despite all that, the popup persists ONLY for DLC maps. Facts:
- The error key `MPUI_PLAYER_DOESNT_HAVE_MAP_PACK` @0x1006eda5 has **ZERO references in RPL
  .text** (robust addis+addi/ori/lwz scan) and is **NOT literal in ui_mp.zone** (decrypted,
  54 MB) nor patch_ui_mp.zone — it's an engine-registered localizedstring shown via a path
  that isn't a plain ownership bool.
- DLC1 content IS present & opens OK at menu init: `dlc1.ipak` (781 MB), `dlc1_load_mp.ff/.ipak`,
  `mp_skate.ipak` (208 MB), and the map zone `mp_skate.ff` exist in BOTH
  `E:\…\content\english\` and the AOC dir `…\0005000c\1010cf00\content\0010\english\`.

CONCLUSION: the residual popup is a **launch-time / content-integrity check**, not an ownership
gate — consistent with the wording "…or the content is **damaged**." The ownership task (this
handoff's scope: make owned content STARTABLE / Start un-greyed) is DONE. The remaining blocker
belongs to the **content-port / map-zone track** (does the converted DLC map .ff actually pass
the loader's validation), not to RPL ownership patching. Flipping more ownership booleans will
not clear it (the last one, PlayerHasDLCForMap, already didn't).

NEXT (evidence needed): fresh Cemu log captured at the exact moment of the popup for a DLC map
— grep the tail for the map's zone request (`mp_skate.ff` etc.), any DB/asset-load fault,
`Sys_Error`, or a failed FSOpenFile right before the dialog. That pins whether the loader
rejects the converted map .ff (integrity) vs a splitscreen/offline DLC restriction.

Tooling note: `tools/ff_decrypt.py` writes the .zone next to its input — run it only on a COPY
placed in scratchpad, never point it at a file under `E:\` (it will write there). Decrypted
ui_mp.zone lives in scratchpad this session.

## STAGE 4 (2026-07-11): fresh log proves popup is pre-launch state, not content load
Fresh Cemu log at the popup moment: the ONLY nn_aoc call is the failed `AOC_Initialize`; there
is **NO `mp_skate.ff` open attempt and NO error/fault of any kind** before the dialog. So the
popup is decided purely from in-memory AOC-populated content state, before any map content is
touched — and via a path that doesn't funnel through the higher-level functions patched in
stages 1-3 (they sit ABOVE the raw state reads). Error key still has 0 refs in RPL .text and is
not literal in ui_mp.zone/patch_ui_mp.zone (relaxed lis+addi/ori/lwz scan allowing rA!=rD).

Root of the AOC-failure: the content subsystem's per-pack state array @~0x1013DDBC (stride 0x9c,
field +0x88 = pack state; owned-mask @0x1013E338) is populated by AOC enumeration / FoundContent,
which never ran. The base predicates that READ it — and that stages 1-3 sat above — are:
- `__Content_DoWeHaveIndexedContentPack` @0x02433f18 (root of Content_GetEnabledContentPacks,
  the "which packs are enabled" value the UI caches)
- `Content_GetContentPackOwnedByMask` @0x02433588 (per-PLAYER owned byte — matches the popup
  wording "PLAYER_DOESNT_HAVE_MAP_PACK")
Both are pure queries (low mount risk; content is present). Patched both → `li r3,1; blr`.
Deployed; backup `t6mp_cafef_rpl.rpl.precontentroot.bak`. FIVE gates now live (verified):
PackIndex, MapPackFlags(-1), PlayerHasDLCForMap, DoWeHaveIndexedContentPack, GetContentPackOwnedByMask.

Awaiting Cemu retest. If the popup CLEARS → the content-pack state read was the gate (done,
ownership fully neutralized). If it PERSISTS → the popup is genuinely not reachable via any
content-ownership predicate, meaning it is decided from a Lua value cached at boot (before these
functions could return owned) or a content-integrity check on the converted map .ff — hand to
the content-port track; further RPL ownership patching is exhausted.

## STAGE 5 (2026-07-11): PC compare empty → treat DLC maps as base via Live_IsMapDLC
User asked to compare the PC build first. Decrypted PC (Plutonium) `ui_mp.ff` + `patch_mp.ff`
(ff_decrypt already has KEY_PC / version 147 auto-detect). The popup key
`MPUI_PLAYER_DOESNT_HAVE_MAP_PACK` is NOT present in PC ui_mp/patch_mp zones either, and the
map-gating Lua tokens (HasDLC/DoesParty/IsMapValid/MapPack) aren't plaintext in the zone → the
gate is engine/event-driven, not a Lua string check. Compare came up empty for the popup gate.

Root understanding: the content system is event-driven — the frontend learns ownership from a
`Content_FoundContent(DlcPackage)` notification fired during AOC enumeration. Cemu stubs nn_aoc,
so FoundContent never fires and the frontend's cached owned-DLC set stays empty; forcing the
low-level READ functions (stages 1-4) doesn't update that cache. Populating the state via the
init/enumeration path is a large multi-structure sub-project (two separate content blocks:
descriptors @0x10f43c8c, owned-state array @0x1013DDBC) and may still not fire the UI event.

CLEANER LEVER TRIED: `Live_IsMapDLC__FPCc` @0x023c4d0c → `li r3,0; blr` (force "not DLC" for
ALL maps). Rationale: base maps work because they're not DLC-classified and skip the ownership
gate entirely; making DLC maps report non-DLC routes them through the identical base-map path,
sidestepping the whole ownership/event problem instead of trying to satisfy it. Base maps
unaffected (already non-DLC). Deployed; backup `t6mp_cafef_rpl.rpl.preismapdlc.bak`.
If the popup consults Live_IsMapDLC (very likely for the "is this a DLC map I must own" branch),
this clears it. If not, fall back to the init/enumeration-population sub-project.

## STAGE 6 (2026-07-11): masks=-1 FROZE menu (reverted); popup reads NONE of the readers
Forcing Content_GetEnabledContentPacks + Content_GetAvailableContentPacks to `li r3,-1`
**froze both MP and ZM menus** (the frontend ITERATES the enabled-packs mask; 0xFFFFFFFF = 32
phantom packs → hang). REVERTED via `t6mp_cafef_rpl.rpl.prelocalmask.bak`. Menu works again.

Definitive negative result: the DLC-map launch popup reads NONE of — PackIndex, PlayerHasDLCForMap,
DoWeHaveIndexedContentPack, GetContentPackOwnedByMask, GetEnabledContentPacks (its correct
non-(-1) value via the DoWeHaveIndexed=1 patch was live in stage 4 and did nothing),
FullPartyMapPackFlags, Live_IsMapDLC. Every content-ownership predicate is exhausted. The fresh
log confirms (again) the popup fires with ZERO filesystem access — pure in-memory, pre-launch.

⇒ The gate is NOT any ownership READER. It is either (a) an event-driven "DLC installed/mounted"
flag set only by the `Content_FoundContent` notification that Cemu's stubbed nn_aoc never fires,
or (b) a Lua check in a menu .ff not yet located (custom-games/combat-training map-select is not
in ui_mp/patch_ui_mp/patch_mp — PC or WiiU). Blind function-flipping is exhausted and now risks
regressions (the freeze). Next must be either a Cemu debugger breakpoint on the popup trigger to
trace the exact caller, OR fixing the ROOT: get Cemu to implement/recognize nn_aoc so AOC
enumeration runs (the aoc title 0005000c IS installed on disk) — that dissolves this entire class.

### CURRENT DEPLOYED STATE (known-good, menu works, popup remains)
Live gates in t6mp_cafef_rpl.rpl: PackIndex=li r3,1 (rows show), FullPartyMapPackFlags=li r3,-1
(Start un-greyed — the real win), PlayerHasDLCForMap=li r3,1, DoWeHaveIndexedContentPack=li r3,1,
GetContentPackOwnedByMask=li r3,1, Live_IsMapDLC=li r3,0. GetEnabled/GetAvailable = ORIGINAL.
Backups per stage: .preownership/.prehasmap/.precontentroot/.preismapdlc/.prelocalmask .bak.

## Coupled prerequisite for DLC2/3/4 to be VISIBLE (not fixed here)
Wii U mapsTable has DLC0+DLC1 rows only. DLC2/3/4 maps won't SHOW until their rows are
added — the patch_mp/patch_zm mapsTable relink job (separate session). Validate this
ownership patch on DLC1 + Nuketown now; confirm DLC2-4 after the relink lands.
