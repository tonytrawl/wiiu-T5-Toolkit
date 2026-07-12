"""Extract ScriptParseTree (compiled GSC/CSC) assets from a decompressed T6 zone.

A ScriptParseTree serializes in the zone stream as the 12-byte struct
    [FFFFFFFF name-ptr][u32 len][FFFFFFFF buffer-ptr]
followed inline by the name (null-terminated) and `len` bytes of compiled
script bytecode (which begins with the magic 0x80 'G' 'S' 'C').

We scan for that struct signature, validate the trailing name and the GSC
magic, and dump each script to disk preserving its in-zone path.
"""
import struct, re, os, sys

FOLLOW = b'\xff\xff\xff\xff'
GSC_MAGIC = b'\x80GSC'
# struct sig: name-ptr(FF*4) + len(4 any) + buffer-ptr(FF*4)
SIG = re.compile(re.escape(FOLLOW) + rb'(....)' + re.escape(FOLLOW), re.DOTALL)


def extract(zone_path, out_dir):
    d = open(zone_path, "rb").read()
    found = []
    for m in SIG.finditer(d):
        length = struct.unpack('>I', m.group(1))[0]
        name_start = m.end()
        nul = d.find(b'\x00', name_start, name_start + 256)
        if nul < 0:
            continue
        name = d[name_start:nul]
        if not re.fullmatch(rb'[\w/.\-]+\.(gsc|csc)', name):
            continue
        buf_start = nul + 1
        buf = d[buf_start:buf_start + length]
        if len(buf) != length or not buf.startswith(GSC_MAGIC):
            continue
        found.append((name.decode(), length, buf))

    print(f"found {len(found)} ScriptParseTree (compiled GSC/CSC) assets")
    for name, length, buf in found:
        dst = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(buf)
    total = sum(l for _, l, _ in found)
    print(f"wrote {len(found)} files ({total} bytes) to {out_dir}/")
    for name, length, _ in sorted(found)[:25]:
        print(f"  {length:>7}  {name}")
    if len(found) > 25:
        print(f"  ... (+{len(found)-25} more)")


if __name__ == "__main__":
    zone = sys.argv[1] if len(sys.argv) > 1 else "../common_mp.zone"
    out = sys.argv[2] if len(sys.argv) > 2 else "../extracted_gsc"
    extract(zone, out)
