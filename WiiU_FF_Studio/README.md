# \# 🎮 Wii U Fastfile Studio

# 

# \[!\[Python Version](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)

# \[!\[Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://github.com/)

# \[!\[Target Game](https://img.shields.io/badge/Game-Black\_Ops\_II\_(T6)-red.svg)](https://en.wikipedia.org/wiki/Call\_of\_Duty:\_Black\_Ops\_II)

# 

# A comprehensive, low-level engineering toolkit and GUI utility for analyzing, modifying, and rebuilding \*\*Black Ops II (T6) Wii U fastfiles (`.ff`)\*\*.

# 

# The Wii U build of T6 packages its zones inside a complex, big-endian, signed, and Salsa20-encrypted container. Because legacy PC and console modding tools fail to read or serialize this specific pipeline correctly, this studio provides a pristine, native Wii U codec, a structural integrity validator, and a deeply customized write-path integration built on top of OpenAssetTools (OAT).

# 

# \---

# 

# \## 🛠️ Feature Architecture

# 

# The core application structures its toolset across six dedicated functional modules:

# 

# 

# ```

# 

# \[ Decrypt ] ─── \[ Repack ] ─── \[ Validate ] ─── \[ Zone Editor ] ─── \[ OAT: Write ] ─── \[ OAT: Read ] ─── \[ OAT: Dump ]

# 

# ```

# 

# \### 🔓 Decrypt \& Decompress

# Extracts raw, decompressed zone data from production Wii U `.ff` containers. 

# \* Parses the authenticated `TAff0100` / version \*\*148\*\* big-endian headers.

# \* Validates the accompanying `PHEEBs71` auth block and 256-byte RSA metadata block.

# \* Unwinds \*\*four interleaved Salsa20 chunk streams\*\*, handling raw-deflate extraction framed exactly on `0x80000` super-block boundaries.

# \* Synchronizes the per-fastfile SHA-1 Initialization Vector (IV) chain seeded by the unique zone name.

# 

# \### 📦 Repack

# Re-serializes modified raw zones back into deployment-ready v148 fastfiles with byte-for-byte fidelity.

# \* Compresses raw zones down into rigid `0x8000` chunk sizes (the hardware-enforced buffer threshold; exceeding this overflows memory and causes hard console freezes).

# \* Encrypts data through parallel Salsa20 streams using appropriate per-stream IVs.

# \* Re-establishes strict hardware-matching super-block padding and alignment constraints.

# 

# \### 🛡️ Structural Validation

# Performs deep-packet pre-flight sanity checks against genuine hardware layout policies before pushing payloads to target systems:

# \* \*\*Memory Blocks:\*\* Verifies `TEMP` remains minimal while persistent asset data maps cleanly to `VIRTUAL`.

# \* \*\*Graph Traversal:\*\* Validates `XAssetList` follow-pointers, the global script-string table, and all localized asset directory records.

# \* \*\*Diff Engine:\*\* Supports optional baseline schema comparison against verified retail reference zones.

# 

# \### 📂 Zone Editor

# An interactive physical inspector for compiled assets.

# \* Scans the data graph to enumerate every compiled script (\*\*GSC/CSC\*\*) and binary \*\*rawfile\*\*.

# \* Offers granular disk export for structural deconstruction, reverse-engineering, or local modification.

# \* Supports \*\*in-place asset replacing\*\*. \*Note: Because zones function as fixed, sequential pointer graphs, replacements must match original byte lengths exactly to maintain structure without a full database compilation.\*

# 

# \### 🚀 OAT: Write, Read \& Dump

# Exposes a custom, extended branch of OpenAssetTools to compile high-level configurations, enumerate console assets, or harvest raw streams:

# \* Automates complex big-endian write-path transformations directly through the interface.

# \* Reads a genuine big-endian Wii U fastfile's assets through the console read path, parsing the Wii U console struct layouts that diverge from the PC layouts (console-layout `Material` at 104 bytes, GX2-based `GfxImage` at 328 bytes, and the technique / GX2 vertex+pixel-shader chain).

# \* Forces extraction via OAT's low-level decompression pipelines, serving as an excellent fallback mechanism when asset dependency graphs cannot be cleanly resolved.

# 

# \---

# 

# \## 📱 Companion Application: Wii U FF Editor

# 

# Included in the repository is `WiiU\_FF\_Editor.exe`—a streamlined, single-purpose application tailored for rapid text asset modifications without intermediary steps.

# 

# \* \*\*Streamlined Pipeline:\*\* Open a `.ff` file directly $\\rightarrow$ edits apply via an interactive, multi-tab text editor (featuring line numbers and global text searching) $\\rightarrow$ save modifications to automatically patch and repack.

# \* \*\*Safety Restraints:\*\* A built-in real-time byte meter tracks local allocations. Shorter strings are padded automatically with null terminators; payload sizes exceeding the original allocation boundaries are strictly blocked to prevent structural corruption.

# \* \*\*Compilation:\*\* Executable builds can be compiled instantly using the included `build\_editor.bat` utility.

# 

# \---

# 

# \## 🔧 Core Enhancements to OpenAssetTools

# 

# Stock OpenAssetTools assumes a little-endian, self-contained PC architecture. To enable complete Wii U operability, this project incorporates an array of low-level patches (controlled dynamically via environment flags):

# 

# | Environment Flag | System Section / Modification | Functional Purpose |

# | :--- | :--- | :--- |

# | `OAT\_WRITE\_WIIU` | \*\*Big-Endian v148 Writer\*\* | Byte-swaps all fundamental primitives, structural pointers, block configurations, and asset metrics during serialization. |

# | \*Auto-Detected\* | \*\*Wii U Fastfile Reader\*\* | Catches `TAff0100` header magic, binds localized Wii U Salsa20 cipher keys, and forces big-endian graph parsing. |

# | `OAT\_WIIU\_BLOCKREMAP` | \*\*Console Struct-Layout Read\*\* | Reads genuine Wii U fastfiles through the console read path: the block remap plus the console struct layouts (`Material` 104 B, GX2 `GfxImage` 328 B, technique / GX2 shader chain) that diverge from the PC definitions. |

# | \*Auto-Remapped\* | \*\*Asset-Type Enum Alignment\*\* | Resolves differences in console asset tables, offsetting shifted structural indices and forcing `MAP\_ENTS` onto console ID \*\*47\*\*. |

# | \*Conditional\* | \*\*Block-Policy Shifting\*\* | Enforces hardware allocation standards by routing default asset arrays to `VIRTUAL` space while preserving local `TEMP` fields. Prevents buffer overruns. |

# | \*Auto-Stripped\* | \*\*Inline Pixel Elimination\*\* | Zeroes out `GfxImageLoadDef::resourceSize` payloads to isolate heavy textures to external IPAK files while preserving necessary metadata headers. |

# | `OAT\_RT\_PHYS=<hex>` | \*\*Physical Memory Reservation\*\* | Appends strict, fixed `RUNTIME\_PHYSICAL` segment allocations directly into output zone headers to emulate retail profiles. |

# | `OAT\_DROP\_GSC`<br>`OAT\_STRIP\_GSC`<br>`OAT\_GSC\_DIR` | \*\*Script Transformation Core\*\* | Controls compiler treatment of `scriptparsetree` items, providing drop, stub, or directory substitution behaviors. |

# | `OAT\_DUMP\_ZONE=<file>` | \*\*Stream Interception Dump\*\* | Intercepts processing pipelines to dump naked, raw decompressed bytes to disk before high-level parsing logic executes. |

# | `OAT\_IGNORE\_SIG` | \*\*Signature Verification Bypass\*\* | Silences non-fatal validation errors on modified or unsigned payloads, ensuring unhindered asset loading. |

# 

# \---

# 

# \## ⚙️ Environment \& Setup

# 

# \### Requirements

# \* \*\*Operating System:\*\* Windows

# \* \*\*Runtime Environment:\*\* Python \*\*3.9+\*\* (Standard library only; no external `pip` dependencies are required for base features).

# \* \*\*Asset Compilation (Optional):\*\* A valid build of the custom, extended OpenAssetTools `Unlinker.exe` placed inside an `oat\\` directory adjacent to the primary module.

# 

# \### Launching the Studio UI

# ```bash

# python wiiu\_ff\_studio.py

# 

# ```

# 

# \*Alternatively, compile a completely isolated, standalone Windows executable by running the native `build.bat` script (see `USAGE.md` for extended parameters).\*

# 

# \### Headless CLI Usage

# 

# For automated pipelines or build environments, headless tools are exposed directly through the command line:

# 

# ```bash

# \# Decrypt a retail container

# python wiiu\_ff.py decrypt <path\_to\_input.ff>

# 

# \# Pack a modified zone folder

# python wiiu\_ff.py pack <path\_to\_zone\_folder> <zone\_name>

# 

# \# Validate structural compliance against a retail reference point

# python zone\_validate.py <path\_to\_target\_zone> --ref <path\_to\_genuine\_zone>

# 

# ```

# 

# \---

# 

# \## ⚠️ Engineering Constraints

# 

# > \[!IMPORTANT]

# > \*\*Cryptographic Integrity:\*\* The 256-byte RSA signature block requires private keys that remain unavailable. Rebuilt fastfiles write null bytes (`0x00`) across this entire allocation block. Successful deployment requires a console-side loader configured with a signature-check bypass or an unsigned-FF execution path.

# 

# > \[!WARNING]

# > \*\*Hardware-Specific Shaders:\*\* Geometry data compiled for distinct GPU microarchitectures cannot be universally translated. This studio processes structures, container formats, metadata blocks, and graph allocations—it does not re-encode hardware-level vertex arrays or asset shaders.

