# HANDOFF — ASSEMBLE: interior model pass 2 → DD share map → gate PASS

Continuation after the 2026-07-10 dockside close (2-map bar MET: dockside walks to EOF,
10,787 anchors → one exact constant 569,444; gate residuals mirror raid). Read
`FINDINGS_runtime_interior_model.md` for your own pass-1 measurements. Three items, in order.

## 1. PC GfxWorld interior virtual model — pass 2 (the DPVS-mirror hypothesis)
Pass 1 falsified the clean image-regions-only premise: image class (probes+lightmaps+
outdoorImage = 10,234,048) lands 63,283 SHORT of the anchor-required 10,297,331. Your own
result (a) names the suspect: the console's runtime allocations are the **mid-asset DPVS
vis-buffer family** (+749,115 before planes) — and every prior result says PC uses the SAME
loader model as console. So the missing PC class is most likely the PC-side DPVS runtime vis
buffers (smodelVisData/surfaceVisData triples etc., runtime-allocated on both platforms per
OAT's loader).
**Check by arithmetic FIRST, before code:** compute expected PC sizes from raid's
smodelCount/surfaceCount (+ per-alloc alignment) and test whether they sum to 63,283. If yes:
model = image-class regions + DPVS runtime class, both derivable from the Track F region
table; encode the PC skip events MID-ASSET (positioned like the console ones — alloc_events
already supports this), verify against the full anchor families on raid, then dockside
(2-map bar applies to the model, as it did to the constants). If the arithmetic does NOT
close, enumerate the remaining runtime-class candidates from OAT's GfxWorld loader (every
`Alloc`-without-file-read site) rather than fitting sizes.

## 2. DD→XModel geometry-share map (last structural violation class)
raid ×6 DDs / 222 pointers; dockside now gives a second oracle (×2 DDs / 293... verify the
counts — 2 DDs, same class). PC content-dedup destroys the share semantics; build the
structural map (which DD piece geometry aliases which source XModel region) from the genuine
side and encode our pointers through it. Byte/pointer-exact vs BOTH oracles.

## 3. Re-judge residuals + declare
After 1–2: re-run both gates. Expected: the clipMap 295 (raid) / 221 (dockside) dedup
residuals in the pre-GfxWorld drift band collapse with the interior model; GWMP ×1 likewise.
If any residual class survives, name it with evidence — do not allowlist unexplained bytes.
Then: **unresolved → 0 on raid AND skate (fatal armed) → declare gate PASS in
PROJECT_STATE.md.** That declaration triggers the main session's go for container authoring
+ patch_zm.

## Small defect to close before the blind build (not after)
**XAnimParts 6-byte under-emit** (dockside-caught): root-cause the converter branch — nothing
proves skate avoids it; that's why the second map exists. The 2 missing dockside techset
corpus blobs are genuinely dockside-only (skate 245/245) — logged, skip.

## Standing
Owned files unchanged (you are sole editor of assemble/converter/gfxworld files). ≥2-map bar
for every new rule. ST calibration must stay exact after every change. Techset-hook blind
path (fires once on skate: hdr_create_lut2dv_827z0f8q) stays a registered boot-#1 unknown —
no action. Never write under `E:\`. Keep PROJECT_STATE/CAVEATS truthful.

## Definition of done
PC interior model anchor-verified on raid + dockside; DD share map exact on both oracles;
residuals collapsed or named; unresolved=0 fatal on raid + skate; **gate PASS declared** —
the linker is then ready for container authoring (next handoff) and the DLC session's
patch_zm go.
