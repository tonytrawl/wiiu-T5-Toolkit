"""Validate skate's DEPLOYED converted .sabl/.sabs structure: header, entry table bounds,
and per-entry format-9 DSP-ADPCM blob headers. A malformed entry offset/size or blob is a
candidate for the AX-voice wild pointer (+0x3817ce)."""
import struct

SND = r'C:/Users/Tony - Main Rig/AppData/Roaming/Cemu/mlc01/usr/title/0005000c/1010cf00/content/0010/sound/'
FILES = ['loaded/mpl_skate.all.sabl', 'mpl_skate.all.sabs']
MAGIC = 0x23585532

for fn in FILES:
    d = open(SND + fn, 'rb').read()
    magic, ver, entrySize, cksumSize, depSize, entryCount, depCount, pad = struct.unpack_from('<8I', d, 0)
    fileSize, entryOffset, cksumOffset = struct.unpack_from('<3Q', d, 0x20)
    print('\n=== %s (%d bytes) ===' % (fn, len(d)))
    print('  magic=%s ver=%d entrySize=%d entryCount=%d depCount=%d' %
          ('OK' if magic == MAGIC else 'BAD 0x%08x' % magic, ver, entrySize, entryCount, depCount))
    print('  fileSize=%d (file=%d %s) entryOffset=0x%x cksumOffset=0x%x' %
          (fileSize, len(d), 'OK' if fileSize == len(d) else 'MISMATCH', entryOffset, cksumOffset))
    if entryOffset + entryCount * 20 > len(d):
        print('  !! entry table out of bounds'); continue
    bad = 0; fmt_hist = {}
    for i in range(entryCount):
        eo = entryOffset + i * 20
        eid, size, off, frames = struct.unpack_from('<4I', d, eo)
        frIdx, ch, loop, fmt = struct.unpack_from('<4B', d, eo + 16)
        fmt_hist[fmt] = fmt_hist.get(fmt, 0) + 1
        # bounds: data region [0x800, entryOffset)
        if off < 0x800 or off + size > len(d) or off + size > entryOffset:
            bad += 1
            if bad <= 5:
                print('  BAD entry %d: id=0x%08x off=0x%x size=%d (past data end 0x%x)' %
                      (i, eid, off, size, entryOffset))
        else:
            # check format-9 blob header BE magic 0x12345678
            if fmt == 9 and size >= 4:
                bm = struct.unpack_from('>I', d, off)[0]
                if bm != 0x12345678 and i < 3:
                    print('  entry %d fmt9 blob magic=0x%08x (want 0x12345678) off=0x%x' % (i, bm, off))
    print('  entries in-bounds: %d bad / %d ; format histogram=%s' % (bad, entryCount, fmt_hist))
