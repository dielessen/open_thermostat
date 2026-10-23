"""Exercise the actual image-size post-action, including ELF/bin padding gap."""
from pathlib import Path
import runpy
import tempfile
import unittest


class Env:
    def __init__(self, root): self.root = root; self.action = None
    def subst(self, key): return 'esp32dev' if key == '$PIOENV' else str(self.root)
    def GetProjectOption(self, key): return 'partitions.csv'
    def AppendUnique(self, **kw): pass
    def AddPostAction(self, target, action): self.action = action


class ActualOtaImage(unittest.TestCase):
    def test_actual_binary_and_both_unequal_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'partitions.csv').write_text('app0,app,ota_0,0x10000,0x1000,\napp1,app,ota_1,0x11000,0x2000,\n')
            env = Env(root)
            runpy.run_path(str(Path(__file__).with_name('esp32_size_link.py')),
                           init_globals={'env':env,'Import':lambda _:None})
            self.assertIsNotNone(env.action)
            image = root/'firmware.bin'
            for size in (1,4096):
                image.write_bytes(b'x'*size); env.action([], [image], env)
            for size in (0,4097):
                image.write_bytes(b'x'*size)
                with self.assertRaises(RuntimeError): env.action([], [image], env)

if __name__ == '__main__': unittest.main()
