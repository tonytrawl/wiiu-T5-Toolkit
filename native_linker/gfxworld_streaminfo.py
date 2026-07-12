#!/usr/bin/env python3
"""
streamInfo synthesis (Track F, Bucket D): the console-only GfxWorldStreamInfo
aabbTrees + leafRefs (~77 KB on raid). REGISTERED SYNTHESIS, not a byte-exact
conversion — the genuine builder's clustering isn't PC-derivable.

Genuine layout (pinned vs mp_raid + mp_dockside oracles, 2026-07-10):
  region = 16 bytes 0xFF (4 pointer words) + treeCount x 48B nodes + leafRefCount
  x u32 leafRefs. NOTE the probe's span boundaries sit -16/-20 off these arrays
  (its aabbTrees span starts at the 0xFF prefix and its leafRefs span starts 16
  bytes before the real array; the "+20 surplus" chased on dockside was this).
  Node 48B (BE): {u32 0, vec3 mins, u32 0, vec3 maxs, u32 0, f32 streamDist2,
  u16 firstItem, u16 itemCount, u16 firstChild, u16 childCount}. Leaf item
  ranges PARTITION [0, leafRefCount); interior nodes carry their subtree's
  (firstItem, itemCount); root's children are contiguous (firstChild,
  childCount) — genuine trees are N-ary (2..9 children).
  leafRefs = static-model indices into dpvs.smodelInsts (genuine has a few
  0x80000-flagged entries and duplicates across leaves; the streaming system
  uses the tree to pick which smodel textures to stream by camera distance).

Synthesis: median-split KD build over smodel bounds centers (bounds from the
PC dpvs.smodelInsts region: 36B GfxStaticModelInst = mins vec3 + maxs vec3 +
lightingOrigin vec3), leaf <= LEAF_MAX items, node bounds = union of member
bounds, streamDist2 = a conservative constant (max observed genuine ~5.8e7).
Structurally valid by the same invariants the genuine trees satisfy.
"""
import struct

LEAF_MAX = 16
STREAM_DIST2 = 6.0e7


def synth_streaminfo(pc, sminst_off, smodel_count):
    """Build console streamInfo from the PC smodelInsts region.
    Returns (region_bytes, tree_count, leafref_count)."""
    insts = []
    for i in range(smodel_count):
        o = sminst_off + i * 36
        mn = struct.unpack_from('<3f', pc, o)
        mx = struct.unpack_from('<3f', pc, o + 12)
        insts.append((mn, mx))

    nodes = []      # (mins, maxs, firstItem, itemCount, firstChild, childCount)
    items = []      # leafRefs in leaf order

    def bounds(idxs):
        mn = [min(insts[i][0][k] for i in idxs) for k in range(3)]
        mx = [max(insts[i][1][k] for i in idxs) for k in range(3)]
        return mn, mx

    # DFS with contiguous child-block allocation: children are allocated as a
    # block (so firstChild/childCount work) and recursed in order (so every
    # subtree's items form a contiguous range — the genuine invariant).
    import sys as _s
    _s.setrecursionlimit(10000)
    nodes.append(None)                       # root placeholder

    def build(ni, idxs):
        mn, mx = bounds(idxs)
        if len(idxs) <= LEAF_MAX:
            fi = len(items)
            items.extend(idxs)
            nodes[ni] = (mn, mx, fi, len(idxs), 0, 0)
            return
        axis = max(range(3), key=lambda k: mx[k] - mn[k])
        s = sorted(idxs, key=lambda i: insts[i][0][axis] + insts[i][1][axis])
        half = len(s) // 2
        parts = [s[:half], s[half:]]
        fc = len(nodes)
        for _ in parts:
            nodes.append(None)
        fi = len(items)
        for j, p in enumerate(parts):
            build(fc + j, p)
        nodes[ni] = (mn, mx, fi, len(idxs), fc, len(parts))
    build(0, list(range(smodel_count)))

    out = bytearray(b'\xff' * 16)
    for mn, mx, fi, ic, fc, cc in nodes:
        out += struct.pack('>I3f', 0, *mn)
        out += struct.pack('>I3f', 0, *mx)
        out += struct.pack('>If', 0, STREAM_DIST2)
        out += struct.pack('>4H', fi, ic, fc, cc)
    for i in items:
        out += struct.pack('>I', i)
    return bytes(out), len(nodes), len(items)


def validate_shape(region, tree_count, leaf_count):
    """Re-check the genuine invariants on a synthesized region."""
    tb = 16
    nodes = []
    for i in range(tree_count):
        o = tb + i * 48
        fi, ic, fc, cc = struct.unpack_from('>4H', region, o + 40)
        nodes.append((fi, ic, fc, cc))
    leaves = [(fi, ic) for fi, ic, fc, cc in nodes if cc == 0]
    leaves.sort()
    ok = leaves[0][0] == 0 and all(leaves[i][0] + leaves[i][1] == leaves[i + 1][0]
                                   for i in range(len(leaves) - 1))
    ok = ok and sum(ic for _, ic in leaves) == leaf_count
    ok = ok and nodes[0][0] == 0 and nodes[0][1] == leaf_count
    return ok
