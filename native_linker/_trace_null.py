"""Trace the skate NULL+0x10 deref (dump 40004): read the exception context (host regs =
Cemu JIT's mapped guest state), disassemble the faulting JIT instruction, and identify
which guest struct pointer is null. Then correlate to the owning asset."""
import struct
DMP = r'C:/CemuFullDumps/Cemu.exe.40004.dmp'
BASE = 0x000002444a8a0000
f = open(DMP, 'rb')
f.seek(8); ns, rva = struct.unpack('<II', f.read(8)); f.seek(rva); dr = f.read(ns*12); stt = {}
for i in range(ns):
    t, s, l = struct.unpack_from('<III', dr, i*12); stt[t] = (s, l)
# Memory64 ranges
s, l = stt[9]; f.seek(l); nn, brva = struct.unpack('<QQ', f.read(16)); f.seek(l+16)
ranges = []; off = brva
for i in range(nn):
    a, z = struct.unpack('<QQ', f.read(16)); ranges.append((a, z, off)); off += z
def rd(host, n):
    for (a, z, fo) in ranges:
        if a <= host < a+z:
            f.seek(fo+(host-a)); return f.read(min(n, a+z-host))
    return None
# Exception stream
s, l = stt[6]; f.seek(l)
tid, al = struct.unpack('<II', f.read(8))
ec, ef, er, ea = struct.unpack('<IIQQ', f.read(24))
npar, _ = struct.unpack('<II', f.read(8)); pars = struct.unpack('<15Q', f.read(120))
ctx_size, ctx_rva = struct.unpack('<II', f.read(8))
print('faultRIP=0x%x accessAddr=0x%x (guest 0x%x)' % (ea, pars[1], pars[1]-BASE if BASE <= pars[1] < BASE+2**32 else pars[1]))
# CONTEXT_AMD64: read GPRs. Offsets in CONTEXT: Rax@0x78,Rcx@0x80,Rdx@0x88,Rbx@0x90,Rsp@0x98,
# Rbp@0xA0,Rsi@0xA8,Rdi@0xB0,R8@0xB8..R15@0xF0, Rip@0xF8
f.seek(ctx_rva); ctx = f.read(ctx_size)
names = ['Rax','Rcx','Rdx','Rbx','Rsp','Rbp','Rsi','Rdi','R8','R9','R10','R11','R12','R13','R14','R15']
regs = {}
for i, nm in enumerate(names):
    regs[nm] = struct.unpack_from('<Q', ctx, 0x78 + i*8)[0]
rip = struct.unpack_from('<Q', ctx, 0xF8)[0]
print('rip=0x%x' % rip)
for i in range(0, 16, 4):
    print('  ' + '  '.join('%s=%016x' % (names[j], regs[names[j]]) for j in range(i, i+4)))
# guest-relative for registers pointing into guest space
print('guest-rel regs (val-BASE if in Wii U space):')
for nm in names:
    v = regs[nm]
    if BASE <= v < BASE+2**32:
        print('   %s = guest 0x%x' % (nm, v-BASE))
# disassemble around faultRIP
code = rd(ea-0x20, 0x60)
if code:
    try:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for ins in md.disasm(code, ea-0x20):
            mark = '  <== FAULT' if ins.address == ea else ''
            print('  %016x %-10s %s%s' % (ins.address, ins.mnemonic, ins.op_str, mark))
    except ImportError:
        print('capstone not installed; raw bytes at faultRIP:', rd(ea, 16).hex())
