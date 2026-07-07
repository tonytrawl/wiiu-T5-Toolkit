#!/usr/bin/env python3
"""Symbolicate Wii U guest addresses against the BO2 RPL .symtab.

Usage:
  rpl_symbolize.py <addr> [<addr> ...]      # name specific guest addresses
  rpl_symbolize.py --threads                # name every thread IP/LR in the
                                            # LAST crashlog in the Cemu log
  rpl_symbolize.py --grep <substr>          # list symbols whose name matches
The RPL path + Cemu log path are the standard install locations.
"""
import bisect
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpl_sigpatch as R

RPL = (r'C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\mlc01\usr\title'
       r'\0005000e\1010cf00\code\t6mp_cafef_rpl.rpl.orig')
LOG = r'C:\Users\Tony - Main Rig\AppData\Roaming\Cemu\log.txt'


def load_syms(path=RPL):
    d = open(path, 'rb').read()
    shoff, N, secs = R._sections(d)
    # find .symtab / .strtab by section type (2 = SYMTAB, 3 = STRTAB after it)
    symtab = strtab = None
    for i, sh in enumerate(secs):
        if sh[1] == 2:                       # SHT_SYMTAB
            symtab = R._sec_bytes(d, sh)
            strtab = R._sec_bytes(d, secs[i + 1])
            break
    if symtab is None:
        raise RuntimeError('no .symtab in RPL')

    def s(off):
        e = strtab.find(b'\x00', off)
        return strtab[off:e].decode('latin-1', 'replace')

    funcs = []
    for o in range(0, len(symtab), 16):
        st_name, st_value, st_size, info, other, shndx = struct.unpack(
            '>IIIBBH', symtab[o:o + 16])
        if st_value and (info & 0xf) == 2:   # STT_FUNC
            funcs.append((st_value, st_size, s(st_name)))
    funcs.sort()
    return funcs


class Symbolizer:
    def __init__(self, funcs):
        self.funcs = funcs
        self.vals = [f[0] for f in funcs]

    def name(self, a):
        i = bisect.bisect_right(self.vals, a) - 1
        if i < 0:
            return '?'
        v, sz, nm = self.funcs[i]
        off = a - v
        if sz and off >= sz:
            return '%#010x = <gap after %s+%#x>' % (a, nm, off)
        return '%#010x = %s+%#x' % (a, nm, off)


def last_crashlog(logpath=LOG):
    d = open(logpath, 'r', errors='replace').read()
    idx = d.rfind('Crashlog for Cemu')
    return d[idx:] if idx >= 0 else ''


def main():
    funcs = load_syms()
    sym = Symbolizer(funcs)
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == '--grep':
        pat = sys.argv[2].lower()
        for v, sz, nm in funcs:
            if pat in nm.lower():
                print('%#010x sz=%#x %s' % (v, sz, nm))
        return
    if sys.argv[1] == '--threads':
        cl = last_crashlog()
        print(cl.splitlines()[1] if len(cl.splitlines()) > 1 else '(no crashlog)')
        # thread lines: "<id> Ent <e> IP <ip> LR <lr> <state> ... Name <name>"
        for m in re.finditer(
                r'^([0-9a-f]{8}) Ent ([0-9a-f]+) IP ([0-9a-f]+) LR '
                r'([0-9a-f]+)\s+(\S+).*?Name (.*)$', cl, re.M):
            tid, ent, ip, lr, state, nm = m.groups()
            print('\n[%s] %-28s %s' % (tid, nm.strip(), state))
            print('  IP ' + sym.name(int(ip, 16)))
            print('  LR ' + sym.name(int(lr, 16)))
        return
    for a in sys.argv[1:]:
        print(sym.name(int(a, 16)))


if __name__ == '__main__':
    main()
