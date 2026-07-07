#!/usr/bin/env python3
"""
Extract XModel surface geometry from a decompressed big-endian (Wii U) T6 zone.

Anchors on XSurface bodies (80 bytes, 32-bit, big-endian), reads vertCount/triCount
from the body, then walks each surface's dynamic data in the order OpenAssetTools'
ZoneCode emits it (the `reorder` in XModel.txt): vertsBlend, tensionData, verts0,
vertList, triIndices. Wii U verts0 are a 24-byte stride (xyz = 3x BE float32, then
12 bytes of packed color/uv/normal/tangent we don't decode here). triIndices are
3x BE uint16. Writes one OBJ per surface group.

Usage: python wiiu_xmodel_extract.py <zone> [out_dir]
"""
import struct, sys, os

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
SURF_SIZE = 80
VTX_STRIDE = 24
TRI_SIZE = 6      # XSurfaceTri = 3x u16
RIGID_SIZE = 12   # XRigidVertList

# alignment of each FOLLOW block type in the stream
A_VERTSBLEND = 2  # u16
A_TENSION = 4     # float
A_VERTS0 = 4      # measured: 24B records, 4-aligned
A_VERTLIST = 4
A_TRI = 16        # XSurfaceTri16

def align(x, a):
    return (x + a - 1) & ~(a - 1)


class Zone:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        self.n = len(self.d)

    def u16(self, o): return struct.unpack('>H', self.d[o:o+2])[0]
    def i16(self, o): return struct.unpack('>h', self.d[o:o+2])[0]
    def u32(self, o): return struct.unpack('>I', self.d[o:o+4])[0]
    def f32(self, o): return struct.unpack('>f', self.d[o:o+4])[0]

    def body(self, o):
        """Parse an XSurface body into a dict, or None if it doesn't look valid."""
        if o + SURF_SIZE > self.n:
            return None
        tri_p = self.u32(o + 12)
        vb0 = self.u32(o + 36)
        ib = self.u32(o + 44)
        flags = self.u16(o + 2)
        vc = self.u16(o + 4)
        tc = self.u16(o + 6)
        v0_p = self.u32(o + 32)
        # strong signature
        if vb0 != 0 or ib != 0:
            return None
        if flags >= 0x100:
            return None
        if not (0 < vc <= 65535 and 0 < tc <= 65535):
            return None
        if tri_p != FOLLOW and not (0 < tri_p < self.n):
            return None
        quantized = bool(flags & 1)
        if not quantized and v0_p != FOLLOW and not (0 < v0_p < self.n):
            return None
        return {
            'off': o, 'tileMode': self.d[o], 'vertListCount': self.d[o+1],
            'flags': flags, 'vertCount': vc, 'triCount': tc,
            'baseVertIndex': self.u16(o + 8),
            'vinfo': [self.i16(o + 16 + 2*k) for k in range(4)],
            'tri_p': tri_p, 'vb_p': self.u32(o + 24), 'td_p': self.u32(o + 28),
            'v0_p': v0_p, 'vl_p': self.u32(o + 40), 'quantized': quantized,
        }

    def plausible_vtx(self, o, count):
        """Check `count` 24B vertices at o are finite, reasonable positions."""
        ok = 0
        for k in range(min(count, 32)):
            x, y, z = struct.unpack('>fff', self.d[o+k*24:o+k*24+12])
            if any(v != v or abs(v) > 5e5 for v in (x, y, z)):
                return False
            ok += 1
        return ok > 0


def find_arrays(z):
    """Find runs of consecutive valid XSurface bodies (the surfs array of a model)."""
    arrays = []
    o = 0
    seen = set()
    while o + SURF_SIZE <= z.n:
        b = z.body(o)
        # require the first body of an array to actually FOLLOW its data (not an alias)
        if b and o not in seen and b['tri_p'] == FOLLOW and (b['quantized'] or b['v0_p'] == FOLLOW):
            run = [b]
            p = o + SURF_SIZE
            while True:
                nb = z.body(p)
                if not nb:
                    break
                run.append(nb)
                seen.add(p)
                p += SURF_SIZE
            arrays.append(run)
            for r in run:
                seen.add(r['off'])
            o = p
        else:
            o += 4
    return arrays


def parse_surface_dyn(z, b, cur):
    """Advance cursor `cur` past one surface's dynamic data, returning (verts, tris, cur)."""
    verts = None
    tris = None
    vc, tc = b['vertCount'], b['triCount']
    vinfo = b['vinfo']
    # 1. vertsBlend (u16) if FOLLOW
    if b['vb_p'] == FOLLOW:
        cnt = vinfo[0] + 3*vinfo[1] + 5*vinfo[2] + 7*vinfo[3]
        cnt = max(cnt, 0)
        cur = align(cur, A_VERTSBLEND) + cnt * 2
    # 2. tensionData (float) if FOLLOW
    if b['td_p'] == FOLLOW:
        cnt = max(vinfo[0] + vinfo[1] + vinfo[2] + vinfo[3], 0)
        cur = align(cur, A_TENSION) + cnt * 4
    # 3. verts0 if present and FOLLOW
    if not b['quantized'] and b['v0_p'] == FOLLOW:
        cur = align(cur, A_VERTS0)
        if not z.plausible_vtx(cur, vc):
            return None, None, cur, False
        verts = [struct.unpack('>fff', z.d[cur+i*24:cur+i*24+12]) for i in range(vc)]
        cur += vc * VTX_STRIDE
    # 4. vertList (XRigidVertList) if FOLLOW; collisionTree pointers nested (assume null in static)
    if b['vl_p'] == FOLLOW:
        cur = align(cur, A_VERTLIST)
        for k in range(b['vertListCount']):
            ct = z.u32(cur + 8)  # collisionTree ptr
            cur += RIGID_SIZE
            if ct == FOLLOW:
                # XSurfaceCollisionTree: 6 floats + u32 + ptr + u32 + ptr = 32B header,
                # then nodes/leafs. Rare in static map props; bail to keep cursor honest.
                return verts, None, cur, False
    # 5. triIndices if FOLLOW
    if b['tri_p'] == FOLLOW:
        cur = align(cur, A_TRI)
        tris = []
        for t in range(tc):
            a = z.u16(cur + (t*3+0)*2)
            bb = z.u16(cur + (t*3+1)*2)
            c = z.u16(cur + (t*3+2)*2)
            tris.append((a, bb, c))
        cur += tc * TRI_SIZE
    return verts, tris, cur, True


def find_vertex_runs(z, min_count=16, min_extent=5.0):
    """Reliable signal: maximal runs of 24B big-endian-float vertices with real
    spatial extent. Real surface geometry has extent; packed-attribute garbage
    misread as positions clusters near zero and is filtered out."""
    d = z.d; n = z.n
    def vok(o):
        x, y, zz = struct.unpack('>fff', d[o:o+12])
        for v in (x, y, zz):
            if v != v or abs(v) > 5e5:
                return False
        return not (x == 0.0 and y == 0.0 and zz == 0.0)
    runs = []
    o = 0
    while o + 72 <= n:
        if vok(o) and vok(o+24) and vok(o+48):
            e = o
            while e + 24 <= n and vok(e):
                e += 24
            cnt = (e - o) // 24
            if cnt >= min_count:
                pts = [struct.unpack('>fff', d[o+k*24:o+k*24+12]) for k in range(cnt)]
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = [p[2] for p in pts]
                ext = ((max(xs)-min(xs))**2 + (max(ys)-min(ys))**2 + (max(zs)-min(zs))**2) ** 0.5
                if ext > min_extent:
                    runs.append((o, pts))
            o = e
        else:
            o += 4
    return runs


def write_pointcloud(z, runs, fn):
    with open(fn, 'w') as fo:
        fo.write("# %s : %d vertex runs, big-endian 24B-stride positions\n" % (fn, len(runs)))
        for o, pts in runs:
            fo.write("o run_0x%07x_n%d\n" % (o, len(pts)))
            for x, y, zz in pts:
                fo.write("v %.5f %.5f %.5f\n" % (x, y, zz))
    print("wrote %s : %d runs, %d verts (open in Blender: File > Import > Wavefront OBJ)"
          % (fn, len(runs), sum(len(p) for _, p in runs)))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'mp_dockside_wiiu.zone'
    out_dir = sys.argv[2] if len(sys.argv) > 2 else 'extracted_models'
    os.makedirs(out_dir, exist_ok=True)
    z = Zone(path)

    # Reliable path: spatially-real vertex runs -> point cloud OBJ (always works).
    runs = find_vertex_runs(z)
    write_pointcloud(z, runs, os.path.join(out_dir, 'positions_pointcloud.obj'))

    # Experimental path: body-anchored surfaces with faces (works where the graph
    # is locally unambiguous; many surfaces are skipped on this build).
    arrays = find_arrays(z)
    print("surfs arrays found (experimental face path): %d" % len(arrays))

    good = 0
    total_surfs = 0
    for ai, run in enumerate(arrays):
        cur = run[0]['off'] + SURF_SIZE * len(run)
        surfs_out = []
        ok_all = True
        for b in run:
            verts, tris, cur, ok = parse_surface_dyn(z, b, cur)
            if not ok or verts is None:
                ok_all = False
                break
            surfs_out.append((b, verts, tris))
        if not surfs_out:
            continue
        # write OBJ for this model (only fully-parsed ones get faces)
        fn = os.path.join(out_dir, "model_%03d_0x%07x.obj" % (ai, run[0]['off']))
        with open(fn, 'w') as fo:
            fo.write("# %s array @0x%x  surfs=%d  fully=%s\n" %
                     (os.path.basename(path), run[0]['off'], len(run), ok_all))
            base = 0
            for b, verts, tris in surfs_out:
                fo.write("o surf_vc%d_tc%d\n" % (b['vertCount'], b['triCount']))
                for x, y, z2 in verts:
                    fo.write("v %.5f %.5f %.5f\n" % (x, y, z2))
                if tris:
                    for a, bb, c in tris:
                        if a < len(verts) and bb < len(verts) and c < len(verts):
                            fo.write("f %d %d %d\n" % (base+a+1, base+bb+1, base+c+1))
                base += len(verts)
        total_surfs += len(surfs_out)
        if ok_all:
            good += 1
        if ai < 12:
            v = sum(len(s[1]) for s in surfs_out)
            t = sum(len(s[2]) for s in surfs_out if s[2])
            print("  model %3d @0x%07x surfs=%d verts=%d tris=%d %s" %
                  (ai, run[0]['off'], len(surfs_out), v, t, "OK" if ok_all else "partial"))
    print("\nwrote models to %s/  (fully-parsed arrays: %d, surfaces extracted: %d)" %
          (out_dir, good, total_surfs))


if __name__ == '__main__':
    main()
