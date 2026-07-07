import struct

wu = open('mp_dockside_wiiu.zone', 'rb').read()
n = len(wu)

def plausible(o):
    if o < 0 or o + 12 > n:
        return False
    x, y, z = struct.unpack('>fff', wu[o:o+12])
    for v in (x, y, z):
        if v != v or abs(v) > 1e5:
            return False
    return True

start = 0x13d139
s = start
while s - 24 >= 0 and plausible(s - 24):
    s -= 24
e = start
while plausible(e):
    e += 24
vcount = (e - s) // 24
print("vertex block: 0x%x..0x%x count=%d stride24" % (s, e, vcount))

# walk back over u16 BE values < vcount immediately preceding the vertex block
p = s
cnt = 0
while p - 2 >= 0:
    v = struct.unpack('>H', wu[p-2:p])[0]
    if v < vcount:
        cnt += 1
        p -= 2
    else:
        break
tri_u16 = cnt - (cnt % 3)
idx_start = s - tri_u16 * 2
print("index u16 before verts: %d (<%d); using %d -> %d tris @0x%x" %
      (cnt, vcount, tri_u16, tri_u16 // 3, idx_start))

verts = [struct.unpack('>fff', wu[s+i*24:s+i*24+12]) for i in range(vcount)]
tris = []
for t in range(tri_u16 // 3):
    a = struct.unpack('>H', wu[idx_start+(t*3+0)*2:idx_start+(t*3+0)*2+2])[0]
    b = struct.unpack('>H', wu[idx_start+(t*3+1)*2:idx_start+(t*3+1)*2+2])[0]
    c = struct.unpack('>H', wu[idx_start+(t*3+2)*2:idx_start+(t*3+2)*2+2])[0]
    if a < vcount and b < vcount and c < vcount:
        tris.append((a, b, c))
print("built %d verts, %d tris" % (len(verts), len(tris)))

with open('dockside_surf0.obj', 'w') as fo:
    fo.write("# extracted from mp_dockside_wiiu.zone, one XSurface, raw BE float32 24B stride\n")
    for x, y, z in verts:
        fo.write("v %.5f %.5f %.5f\n" % (x, y, z))
    for a, b, c in tris:
        fo.write("f %d %d %d\n" % (a+1, b+1, c+1))
print("wrote dockside_surf0.obj")

xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
print("bbox X[%.2f,%.2f] Y[%.2f,%.2f] Z[%.2f,%.2f]" %
      (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
