import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_hacs_repo


class HacsFrontPageTest(unittest.TestCase):
    def test_hacs_json_hides_the_default_branch(self):
        # Every release is a pre-release; without this HACS offers the main-branch commit as an update.
        with tempfile.TemporaryDirectory() as tmp:
            publish_hacs_repo.write_front_page(Path(tmp))
            hacs = json.loads((Path(tmp) / "hacs.json").read_text(encoding="utf-8"))
        self.assertIs(hacs["hide_default_branch"], True)
        self.assertEqual(hacs["name"], "OpenThermostat")
        self.assertIs(hacs["render_readme"], True)


if __name__ == "__main__":
    unittest.main()
