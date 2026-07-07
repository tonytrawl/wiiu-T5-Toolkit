import struct

wu = open('mp_dockside_wiiu.zone', 'rb').read()
n = len(wu)
FOLLOW = 0xFFFFFFFF

def u16(o): return struct.unpack('>H', wu[o:o+2])[0]
def u32(o): return struct.unpack('>I', wu[o:o+4])[0]

# XSurface body (80B, BE, 32-bit) field offsets:
#  0 tileMode(1) 1 vertListCount(1) 2 flags(u16) 4 vertCount(u16) 6 triCount(u16)
#  8 baseVertIndex(u16) 10 pad 12 triIndices* 16 vertCount[4](i16) 24 vertsBlend*
#  28 tensionData* 32 verts0* 36 vb0* 40 vertList* 44 indexBuffer* 48 partBits[5](20) ->68 pad->80
def looks_body(o):
    if o + 80 > n: return False
    if u32(o+12) != FOLLOW: return False      # triIndices FOLLOW
    if u32(o+36) != 0: return False            # vb0 never -> 0
    if u32(o+44) != 0: return False            # indexBuffer never -> 0
    vc = u16(o+4); tc = u16(o+6)
    if not (0 < vc <= 50000 and 0 < tc <= 50000): return False
    v0 = u32(o+32)
    flags = u16(o+2)
    # verts0 present unless quantized(flag bit0). If present must be FOLLOW or alias(<n), if quantized must be 0
    if not (flags & 1):
        if v0 != FOLLOW and not (0 < v0 < n): return False
    return True

bodies = []
o = 0
while o + 80 <= n:
    if looks_body(o):
        bodies.append(o)
        o += 4
    else:
        o += 4
print("candidate XSurface bodies:", len(bodies))
for o in bodies[:12]:
    tm=wu[o]; vlc=wu[o+1]; flags=u16(o+2); vc=u16(o+4); tc=u16(o+6); bvi=u16(o+8)
    vinfo=[struct.unpack('>h',wu[o+16+2*k:o+18+2*k])[0] for k in range(4)]
    vb=u32(o+24); td=u32(o+28); v0=u32(o+32); vl=u32(o+40)
    print("@0x%07x tile=%d vlc=%d flags=0x%x vCount=%d triCount=%d baseVI=%d vinfo=%s vb=%s td=%s v0=%s vl=%s o%%16=%d" % (
        o,tm,vlc,flags,vc,tc,bvi,vinfo,
        'F' if vb==FOLLOW else ('0' if vb==0 else hex(vb)),
        'F' if td==FOLLOW else ('0' if td==0 else hex(td)),
        'F' if v0==FOLLOW else ('0' if v0==0 else hex(v0)),
        'F' if vl==FOLLOW else ('0' if vl==0 else hex(vl)),
        o%16))
