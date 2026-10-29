"""Exercise the l32r literal reach guard on synthetic ELF objects and its link hook."""
from pathlib import Path
import runpy
import struct
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('e32v2_literal_reach.py')
guard = runpy.run_path(str(SCRIPT), run_name='literal_reach')


def elf(sections):
    """A minimal ELF32 LE relocatable with the given (name, size, flags, type) sections."""
    names = b'\0' + b''.join(name.encode() + b'\0' for name, *_ in sections) + b'.shstrtab\0'
    headers, offset, position = [bytes(40)], 52, 1
    for name, size, flags, kind in sections:
        headers.append(struct.pack('<IIIIIIIIII', position, kind, flags, 0, offset, size, 0, 0, 4, 0))
        position += len(name) + 1
    headers.append(struct.pack('<IIIIIIIIII', position, 3, 0, 0, 52, len(names), 0, 0, 1, 0))
    shoff = 52 + len(names)
    head = b'\x7fELF\x01\x01\x01' + bytes(9) + struct.pack('<HHIIIIIHHHHHH', 1, 94, 1, 0, 0, shoff, 0, 52, 0, 0, 40,
                                                            len(headers), len(headers) - 1)
    return head + names + b''.join(headers)


def code(name, size): return (name, size, 0x6, 1)          # SHF_ALLOC|SHF_EXECINSTR, PROGBITS
def data(name, size): return (name, size, 0x3, 8)          # NOBITS: never counted


class Env:
    def __init__(self, build): self.build = build; self.action = None
    def subst(self, key): return {'$PIOENV': 'e32v2', '$BUILD_DIR': str(self.build)}.get(key, key)
    def AddPreAction(self, target, action): self.target = target; self.action = action


class LiteralReach(unittest.TestCase):
    def test_separate_literal_sections_count_the_whole_object(self):
        row = guard['reach'](elf([code('.literal.a', 1000), code('.text.a', 3000), code('.text.b', 500),
                                  code('.literal.empty', 0), data('.bss.x', 10**6)]))
        self.assertEqual(row, {'literal': 1000, 'text': 3500, 'largest_text': 3000, 'reach': 4500})

    def test_text_section_literals_count_the_largest_function(self):
        row = guard['reach'](elf([code('.text.a', 3000), code('.text.b', 500), code('.iram1.0', 9000)]))
        self.assertEqual(row['reach'], 3000)

    def test_build_directory_and_failure_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)
            (build / 'src/update').mkdir(parents=True)
            (build / 'src/main.cpp.o').write_bytes(elf([code('.literal.a', 96000), code('.text.a', 110000)]))
            (build / 'src/update/small.cpp.o').write_bytes(elf([code('.literal.a', 10), code('.text.a', 90)]))
            (build / 'libother.a').write_bytes(b'not checked')
            rows, failures = guard['check'](build)
            self.assertEqual([row['object'] for row in rows], ['src/main.cpp.o', 'src/update/small.cpp.o'])
            self.assertEqual([row['object'] for row in failures], ['src/main.cpp.o'])
            self.assertIn('-mtext-section-literals', guard['report'](rows, failures))
            self.assertEqual(guard['main'](['x', str(build)]), 1)
            (build / 'src/main.cpp.o').write_bytes(elf([code('.text.a', 110000), code('.text.b', 150000)]))
            self.assertEqual(guard['check'](build)[1], [])
            self.assertEqual(guard['main'](['x', str(build)]), 0)
            self.assertEqual(guard['main'](['x', str(build / 'missing')]), 1)

    def test_link_hook_blocks_the_e32_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)
            (build / 'src').mkdir()
            env = Env(build)
            runpy.run_path(str(SCRIPT), init_globals={'env': env, 'Import': lambda _: None})
            self.assertEqual(env.target, '$BUILD_DIR/${PROGNAME}.elf')
            (build / 'src/main.cpp.o').write_bytes(elf([code('.text.a', 1000)]))
            env.action([], [], env)
            (build / 'src/main.cpp.o').write_bytes(elf([code('.literal.a', 1000), code('.text.a', 204000)]))
            with self.assertRaises(RuntimeError):
                env.action([], [], env)

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            guard['reach'](b'!<arch>\n')


if __name__ == '__main__':
    unittest.main()
