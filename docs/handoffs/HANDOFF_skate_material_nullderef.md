# HANDOFF (FRESH SESSION) — skate material-registration NULL-deref

**Goal:** find and fix the guest NULL-pointer deref that is the CURRENT skate boot blocker,
after the audio-endian and tail-layout crashes were cleared (2026-07-12). This is the ONLY
thing between skate and (at least) the next boot layer.

Read `HANDOFF_session_2026-07-12_sndbank_skate_layout.md` §3 for how we got here (measured
tail-anchor layout method). You do NOT need the SndBank/raid history to work this.

═══════════════════════════════════════════════════════════════════════════════
## THE CRASH (dump 40004, base 0x000002444a8a0000)
═══════════════════════════════════════════════════════════════════════════════
Guest-JIT fault (NO Cemu crashlog — recompiled-guest fault). 760 frames rendered, then during
FS streaming right after our mp_skate.ff loads (shared banks mpl_common/mpl_code_post_gfx loaded
clean first). code=0xc0000005, accessAddr = **guest 0x10** = read of [null + 0x10].

Faulting JIT instruction (from _trace_null.py, capstone disasm of the JIT code at faultRIP):
```
  movbe esi, [r13 + rbx + 4]        ; esi = guest[rbx+4]  (=rsi 0x128dbaa0)
  movbe r8d, [r13 + rdi + 8]        ; r8d = guest[rdi+8]   <== FAULT, rdi=8 (from [rsp+0x74])
  movbe ecx, [r13 + rsi + 0x10c4]   ; ecx = guest[rsi+0x10c4]  (a shader-name ptr)
  cmp  ecx, r8d
  sete byte [rsp+0x28e]             ; bool = (shaderA == shaderB)
```
(r13 = guest base; guest ptr P is accessed as [r13+P]. So rdi is a guest pointer = 8 = garbage.)

Register context at fault: Rdi=8, Rsi=0x128dbaa0, Rbx=0x4e61fe90, Rcx=0, R13=guest base.
- rbx (0x4e61fe90) holds {0x128dcba0, 0x128dbaa0} — two sibling structs 0x1100 apart; the loop
  iterates PAIRS. rsi = the 2nd (rbx+4).
- rsi struct (0x128dbaa0): a >4KB RUNTIME struct — first word BE count 0xe2=226, then an array of
  BE-1 flags; field @+0x10c4 is a ptr (0x30e21e4c) → data "pimp_shader_vertcolorsimple_fa4ae256.hls"
  (a shader name). So rsi is a per-material/technique RUNTIME REGISTRY the engine builds at load,
  keyed by/holding shader names, and it's doing a shader-equality dedup/match where the OTHER
  operand's struct ptr (rdi) is null.
- rdi = [rsp+0x74] = 8. WHERE rdi got 8 is NOT yet traced — the next lead (see below).

═══════════════════════════════════════════════════════════════════════════════
## WHAT IS ALREADY RULED OUT (don't re-do)
═══════════════════════════════════════════════════════════════════════════════
- NOT a layout/relocation crash: host relocation crashes (+0x20a436/+0x20b6aa) are GONE after the
  35-anchor tail map. This is a NULL deref, different class.
- NOT a bad techset SLOT value: all 241 standalone MaterialTechniqueSet blobs have 32-slot arrays
  that are FOLLOW(4828)/0(2884) only — ZERO garbage, ZERO aliases (incl. the techset owning the
  crash shader, span 0x21a4e-0x444f9 in mp_skate_measured.zone).
- NOT a foreign-alias technique slot: standalone MTS have NO alias slots at all; the INLINE GfxWorld/
  material techsets are GENUINE console corpus blobs (produce_nobackbone._inline_ts_hook → techset_
  translate corpus) = structurally valid. So no alias mis-resolution in techsets.
- ⇒ rdi=8 is NOT a converter techset field-emit bug. It's a deeper RUNTIME registry null.

═══════════════════════════════════════════════════════════════════════════════
## ✅ RESOLVED 2026-07-12 — convergence check = NO. Root fully re-traced.
═══════════════════════════════════════════════════════════════════════════════
The XModel-inline-image convergence was CHECKED and RULED OUT. Evidence:
- Re-traced rdi's origin (native_linker/_trace_rdi3.py, disasm from faultRIP-0x400): the fault
  addr guest 0x10 = `[rsi+0x98] + 8 + r9*0x18 + 8` with `[rsi+0x98]==0` and `r9==0`. The rsi
  struct @guest 0x128dbaa0 has TWO parallel (ptr,count) arg arrays: +0x90 arrayA=0x10497558
  count(+0x94)=2 PRESENT; +0x98 arrayB=NULL count(+0x9c)=8. Engine iterates 8 entries off a
  NULL base → null+0x10. (The handoff's earlier "sibling pair 0x1100 apart" reading was WRONG —
  that region is just float data 0x3f800000=1.0.)
- Classified the crash shader's owner in the PC source (native_linker/_classify2.py): ALL 9
  `pimp_shader_vertcolorsimple*` occurrences — incl. the exact crash variant fa4ae256 (PC
  0x29693) — live inside STANDALONE MaterialTechniqueSet bodies (idx5 [169395..444255], name
  `mc_lit_sm_t0c0_90wz6fe2`), ZERO inside any XModel body. So the crash material is NOT an
  XModel inline material. Completing the XModel inline-image emit will NOT clear this crash;
  the two threads are SEPARATE roots.
- That techset got an **exact** Track-B corpus substitution (genuine console blob, verbatim),
  NOT struct/prefix — so it's also not an approximate-substitute layout mismatch.
⇒ ACTUAL BUG (leading hypothesis, needs verifying in the blob): a MaterialPass argument-array
  INTERIOR pointer inside the exact-substituted genuine techset blob is left null/unrelocated
  by the assembler (count 8 preserved, base pointer dropped) — i.e. a techset-interior arg-ptr
  relocation gap, deeper than the 32-slot technique-array check the earlier ruling-out covered.
  NEXT = inspect mc_lit_sm_t0c0_90wz6fe2's console blob MaterialPass.args interior ptr in the
  assembled zone (measured.zone MTS span ~0x21a4e-0x444f9) and confirm whether it's relocated.

── UPDATE 2 (2026-07-12, same session): arg-ptr-relocation hypothesis REFUTED. ──
Verified the emitted techset directly (native_linker/_tsdiff.py):
- The assembled techset body @0x21a4e in mp_skate_measured.zone is **BYTE-IDENTICAL to the
  genuine corpus blob for all 141995 bytes (0 diffs)**. The crash pass = technique@74229 pass0,
  arg-group counts (5,1,8) [byte@po+12/13/14], args_p @po+20 = FOLLOW — emitted VERBATIM. So the
  assembler does NOT drop/corrupt the pass args pointer or its inline literal-const data. The
  techset emit is NOT the bug.
- The count 8 (the null arrayB's count) = the third arg-group of that pass (5,1,8). But since the
  techset streams it correctly (FOLLOW + inline data, byte-perfect), the loader should build it.
⇒ The null [rsi+0x98] is therefore on the MATERIAL / runtime-registry side, not the techset. The
  runtime struct @0x128dbaa0 is a per-material record the engine builds+dedups (two tables: +0x90
  present/cnt2, +0x98 null/cnt8, shader name +0x10c4). BUT: material_convert.py emits the two
  table pointers via reloc() preserving FOLLOW, and is raid-oracle-VALIDATED 352/352 on GfxWorld
  inline materials — so a plain dropped constantTable pointer is unlikely too.
OPEN LEADS (both untested):
  (a) Runtime-registry builder: what allocates the count-226, shader-name@+0x10c4 struct at load?
      The null arrayB may be a runtime-derived sampler/constant array the engine builds by matching
      the material's textureTable/constantTable against the shader's expected args — a MISMATCH
      (material provides fewer than the shader's 8) could leave it null. Trace what writes +0x98.
  (b) ipak-streamed IMAGE convergence (DIFFERENT from the XModel-inline path already ruled out):
      if arrayB is a per-material sampler array built from textureTable, a material texture that
      failed to load from mp_skate.ipak would null it. Check the crash material's textures resolve
      in the ipak. NOTE this is the streamed-ipak image path, not XModel-inline.

── UPDATE 3 (2026-07-12): (a)-vs-(b) DISAMBIGUATED via static arg-type read = (b), image path. ──
Reconciliation: dump 40004 is the NEWEST skate dump (15:30, matches deployed measured.ff 15:29).
Signature `movbe r8d,[r13+rdi+8]` (BE dword, shader-arg compare) is DIFFERENT from the CSV-parser
derefs (36196/37608, `movzx ebx,[r13+rdx]`, now rotated out). => skate ADVANCED past the CSV wall
to a NEW material/texture wall = real forward progress, not re-analysis.
Dumped the crash pass's 14 args from the byte-perfect techset (native_linker/_args.py,
technique@74229 pass0, groups (5,1,8)): 7xtype3 CODE_PIXEL_CONST, 1xtype2 MATERIAL_PIXEL_SAMPLER
(arg6, sampler nameHash 0xa0ab1041), 4xtype4 MATERIAL_PIXEL_CONST, 2xtype5 CODE_PIXEL_SAMPLER.
=> The null count-8 "stable" arg array CONTAINS a MATERIAL sampler the engine resolves to a LOADED
IMAGE. Techset byte-perfect => arg count/def correct => NOT (a) count-reconciliation. The failure
is in RESOLVING the material sampler -> image = the IMAGE/TEXTURE path = (b), same class the raid
XModel-inline-image drop proves with an oracle.
WHICH image path (fix routing): crash material `mc_lit_sm_t0c0` = a lit WORLD-surface material,
most likely GfxWorld-inline (or ipak-streamed), NOT XModel-inline. Raid ground-truth is XModel-
inline (skybox). THREE image paths exist (XModel-inline, GfxWorld-inline resident
[[gfxworld-resident-image-gap]], ipak-streamed) => confirm skate's dropped image is in the
GfxWorld-inline/ipak path before assuming the XModel-inline fix alone clears skate.
NEXT = (1) check whether the mc_lit_sm sampler texture (hash 0xa0ab1041) is resident/inline vs
ipak-streamed and whether our emit/ipak provides it; (2) run the raid XModel-inline-image fix loop
(oracle) in parallel; rebuild+retest skate — if +0x98 clears, (b) confirmed and the paths unify.

─── original note (kept for context) ───
═══════════════════════════════════════════════════════════════════════════════
## ★ CHECK THIS FIRST — possible convergence with the XModel dropped-inline-image bug
═══════════════════════════════════════════════════════════════════════════════
Two threads may be the SAME root. The raid-control finding [[pipeline-fails-raid-control]]:
the XModel converter DROPS large inline-material images (skybox_mp_raid emits 15KB vs genuine
1.59MB; 36/440 XModels under-emit −3.68MB total) — and crucially the STANDALONE Material path
was FINE; ONLY the XModel-INLINE-material path drops/under-emits. A NULL-deref specifically in
MATERIAL/TECHSET registration is exactly the failure shape a dropped/malformed inline-material
image or techset would produce. (Consistent with what we ruled out here: standalone MTS + the
GfxWorld inline corpus techsets are clean — but XModel inline materials are a THIRD path neither
of those checks covered.)
CHEAP, HIGH-VALUE FIRST TEST: is the material being registered at the crash (the one carrying
shader 'pimp_shader_vertcolorsimple', or whichever rsi-registry entry) one whose inline image or
techset was DROPPED/under-emitted by the XModel converter?
  - Cross-ref the crash material against the 36 under-emitting XModels (see
    [[pipeline-fails-raid-control]] / the XModel inline-material image-emit gap; Track C remaining
    item = "inline-material images (image track)", trackC-xmodel-converter.md).
  - Check whether skate XModels carry inline materials whose image/techset emit is truncated
    (compare emitted inline-material size vs expected, like the raid skybox 15KB-vs-1.59MB test).
IF YES → the raid-control fix (complete XModel inline-material image/techset emit, image track)
  and THIS skate blocker are the SAME bug; fixing the inline-image emit clears BOTH. Highest-value
  outcome — do this before deep JIT tracing.
IF NO → it's a genuinely separate registration bug; proceed to the trace steps below.

═══════════════════════════════════════════════════════════════════════════════
## NEXT STEPS (in order, if the convergence check above is NO)
═══════════════════════════════════════════════════════════════════════════════
1. **Trace rdi's origin.** rdi = [rsp+0x74]. Disassemble the JIT function BACKWARD from the fault
   (extend _trace_null.py: disasm from faultRIP-0x400) to find where [rsp+0x74] is written and what
   guest load produced 8. That reveals which guest struct field / array index yields the null. The
   value 8 (not 0) suggests an INDEX or a small-offset field, not a plain null pointer.
2. **Identify the +0x10c4 registry.** It's a >4KB runtime struct (count 226, flag array, shader-name
   @+0x10c4), built at load. Figure out which engine subsystem builds it — candidates: the material/
   technique sort-key registry, the GfxWorld surface→material batch table, or a shader-permutation
   cache. 226 ≈ a count of unique materials/techsets/shaders in the skate scene. Search the guest
   for what allocates/populates a 0x1100-stride struct array.
3. **Find the missing/null referenced asset.** The registry entry is null because a material→X
   runtime lookup returned null. Likely X = an IMAGE (material texture that failed to load/register),
   a sort-key material, or a technique permutation. Check whether any skate material references an
   asset that our converter dropped or mis-named (esp. inline-material IMAGES — the XModel/GfxWorld
   inline-image emit was historically incomplete; see xmodel-inline-image-transplant.md).
4. **Cross-check with the OLDER skate null-deref** [[skate-boot-nullderef-not-layout]] (2026-07-11):
   that one was a char==',' CSV/StringTable parser NULL deref (movzx ebx,[r13+rdx], rdx=0). THIS one
   is different (shader compare, +0x10c4), so the layout fix advanced PAST the CSV one — but confirm
   the CSV one is actually gone (it may resurface at a different frame).

═══════════════════════════════════════════════════════════════════════════════
## TOOLS / MECHANICS
═══════════════════════════════════════════════════════════════════════════════
- `native_linker/_trace_null.py` — reads a dump's ExceptionStream (host regs = JIT-mapped guest
  state) + Memory64List, disassembles the JIT fault with capstone, prints guest-rel registers.
  Edit DMP/BASE at top for a new dump (base from Cemu log "Init Wii U memory space (base: …)").
- Regenerate a skate dump: skate is deployed at 0005000c/…/0010/english/mp_skate.ff; boot Cemu →
  it crashes → new C:\CemuFullDumps\Cemu.exe.<pid>.dmp. Dumps rotate out fast — grab the base+rip
  from the fresh Cemu log immediately.
- Zone to inspect: native_linker/mp_skate_measured.zone (matches the deployed .ff).
- Guest memory read helper pattern (guest addr → dump bytes) is in _trace_null.py / _measure_sndpos.py.
- USE `python` not `python3`. Read Cemu log rip, NOT the WER ExceptionStream (first-chance).

═══════════════════════════════════════════════════════════════════════════════
## SUCCESS = skate advances past the NULL+0x10 deref (760-frame point).
═══════════════════════════════════════════════════════════════════════════════
If a NEW crash appears after fixing this, re-run the tail-anchor loop if it's a relocation crash
(layout shifts with content changes), or trace the new fault. The layout method is repeatable and
documented in the main handoff §3.

── UPDATE 4 (2026-07-12): sampler hash identified + router correction. ──
0xa0ab1041 = R_HashString("colorMap") (wiiu_ref/ipak.py r_hash_string; confirmed exact). It is a
SAMPLER-SEMANTIC hash, appears 4851x in mp_skate_pc.zone, and is NOT an ipak image key (skate has
1029 hash-validated GfxImages; colorMap is not one). => The null count-8 stable-arg array includes
the BASE DIFFUSE colorMap sampler; building it needs the material's colorMap resolved to a LOADED
image. Missing/stubbed base-diffuse => null array => crash. Strongly (b).
ROUTER FIX: do NOT look up 0xa0ab1041 in the ipak (false negative — it's a semantic). Chain =
crash material -> its MaterialTextureDef{nameHash=colorMap} -> image ptr -> actual image (one of
1029) -> that image's OWN name-hash -> check ipak/GfxWorld-resident emit. Productive test = CLASS
check: are skate's colorMap-class images emitted with real data vs stubbed, on both GfxWorld-
resident ([[gfxworld-resident-image-gap]]) and ipak-streamed paths? Raid GfxWorld resident images
are an ORACLE for the GfxWorld-resident path too => validate that fix on raid, not skate-blind.
Pinning the EXACT image needs the specific crash material; the runtime reflection struct @0x128dbaa0
exposes no material-name ptr (guest-side still trying to recover the bound image ptr from it).
