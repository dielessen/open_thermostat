"""Keep every E32 application object within the Xtensa l32r literal reach.

An l32r instruction loads a literal at most 256 KiB before itself. GCC puts
the literal pools of a translation unit in separate .literal.* sections, all
ahead of its .text.* sections. The linker interleaves most of them with their
functions, but not reliably: in beta.19 main.cpp.o (about 499 KB) linked only by
chance, with pollSetupWifi 256,099 bytes after its literals, and a slightly
different tree failed with "dangerous relocation: l32r: literal target out of
range". platformio.ini therefore builds the application sources (only those,
see build_src_flags) with -mtext-section-literals: each function carries its
own pool, so the distance is bounded by that function's size.

This check fails when an application object can again place literals further
than LIMIT from the code that loads them: worst case, all literal and text
sections of one object in a row, or one function larger than LIMIT with
text-section literals. Vendor and library objects are not checked (they are
reviewed byte for byte elsewhere and are far smaller).

PlatformIO runs this before the E32 link (post: extra script). Standalone:
    python scripts/e32v2_literal_reach.py [.pio/build/e32v2]
"""
from pathlib import Path
import struct
import sys

LIMIT = 200 * 1024  # l32r reaches 256 KiB; keep a margin for growth.


def sections(data):
    """(name, size) of the allocated sections of an ELF32 little-endian object."""
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise ValueError("not an ELF32 little-endian object")
    shoff, = struct.unpack_from("<I", data, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x2E)
    headers = [struct.unpack_from("<IIIIIIIIII", data, shoff + i * shentsize) for i in range(shnum)]
    strings = headers[shstrndx]
    names = data[strings[4]:strings[4] + strings[5]]
    out = []
    for name, kind, flags, _, _, size, *_ in headers:
        if flags & 0x2 and kind != 8 and size:  # SHF_ALLOC, not NOBITS
            out.append((names[name:names.index(b"\0", name)].decode(), size))
    return out


def reach(data):
    """Worst-case distance from a literal to the code that loads it, in bytes."""
    literal = text = largest = 0
    for name, size in sections(data):
        if name == ".literal" or name.startswith(".literal."):
            literal += size
        elif name == ".text" or name.startswith(".text."):
            text += size
            largest = max(largest, size)
    return {"literal": literal, "text": text, "largest_text": largest,
            "reach": literal + text if literal else largest}


def check(build, limit=LIMIT):
    """Return (rows, failures) for the application objects of a build directory."""
    rows = []
    for path in sorted((Path(build) / "src").rglob("*.o")):
        rows.append(dict(reach(path.read_bytes()), object=str(path.relative_to(build))))
    rows.sort(key=lambda row: -row["reach"])
    return rows, [row for row in rows if row["reach"] > limit]


def report(rows, failures, limit=LIMIT):
    lines = [f"l32r literal reach (limit {limit} bytes of 262141):"]
    lines += [f"  {row['reach']:7d}  {row['object']} (literal {row['literal']}, text {row['text']}, "
              f"largest function {row['largest_text']})" for row in rows[:3]]
    for row in failures:
        lines.append(f"FAIL {row['object']}: literals can end up {row['reach']} bytes before their code. "
                     "Build application sources with -mtext-section-literals (build_src_flags) "
                     "and keep functions below the limit.")
    return "\n".join(lines)


def main(argv):
    build = Path(argv[1] if len(argv) > 1 else ".pio/build/e32v2")
    rows, failures = check(build)
    if not rows:
        print(f"No application objects in {build}/src")
        return 1
    print(report(rows, failures))
    return 1 if failures else 0


try:
    Import("env")  # noqa: F821 - PlatformIO extra script
except NameError:
    env = None

if env is not None and env.subst("$PIOENV") == "e32v2":
    def before_link(source, target, env):
        rows, failures = check(env.subst("$BUILD_DIR"))
        print(report(rows, failures))
        if failures:
            raise RuntimeError("E32 application object exceeds the l32r literal reach margin")
    env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", before_link)
elif __name__ == "__main__":
    sys.exit(main(sys.argv))
