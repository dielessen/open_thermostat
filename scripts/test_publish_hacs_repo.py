import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_hacs_repo

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
TRAILER = "Co-Authored-By: Some Session <session@example.invalid>"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


def make_clone(root, origin=publish_hacs_repo.HACS_REMOTE):
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, env={**os.environ, **GIT_ENV})
    git(root, "remote", "add", "origin", origin)
    (root / "README.md").write_text("old\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    return root


def package(version):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("custom_components/open_thermostat/manifest.json", json.dumps({"domain": "open_thermostat", "version": version}))
        archive.writestr("custom_components/open_thermostat/__init__.py", "# integration\n")
        archive.writestr("LICENSE", "MIT\n")
        archive.writestr("RELEASE-NOTES.md", f"# HA {version}\n")
        archive.writestr("SOURCE.json", "{}\n")
        archive.writestr("notices/PLATFORM.txt", "not copied\n")
    return buffer.getvalue()


class HacsFrontPageTest(unittest.TestCase):
    def test_hacs_json_hides_the_default_branch(self):
        # Every release is a pre-release; without this HACS offers the main-branch commit as an update.
        with tempfile.TemporaryDirectory() as tmp:
            publish_hacs_repo.write_front_page(Path(tmp), "1.0.0rc5", "rc4")
            hacs = json.loads((Path(tmp) / "hacs.json").read_text(encoding="utf-8"))
        self.assertIs(hacs["hide_default_branch"], True)
        self.assertEqual(hacs["name"], "OpenThermostat")
        self.assertIs(hacs["render_readme"], True)

    def test_front_page_takes_its_example_version_and_screenshots_from_the_arguments(self):
        # R5-17: nothing of an earlier release is written in the template.
        with tempfile.TemporaryDirectory() as tmp:
            publish_hacs_repo.write_front_page(Path(tmp), "1.0.0rc5", "rc4")
            readme = (Path(tmp) / "README.md").read_text(encoding="utf-8")
        self.assertIn("(such as `1.0.0rc5`)", readme)
        for name in publish_hacs_repo.SCREENSHOTS:
            self.assertIn(f"/docs/img/screenshots/{name}-rc4.png", readme)
        self.assertNotIn("rc2", readme)
        self.assertNotIn("{", readme.replace("{{", "").replace("}}", ""), "an unfilled placeholder")
        self.assertNotIn("\r", readme)

    def test_the_screenshots_of_the_front_page_exist_in_the_project(self):
        sets = publish_hacs_repo.screenshot_sets(Path(__file__).resolve().parents[1] / "docs" / "img" / "screenshots")
        self.assertTrue(sets, "no complete screenshot set")
        self.assertEqual(publish_hacs_repo.default_screenshots(), sets[-1])

    def test_the_newest_complete_screenshot_set_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            for suffix, names in (("rc2", publish_hacs_repo.SCREENSHOTS), ("rc4", publish_hacs_repo.SCREENSHOTS),
                                  ("rc10", publish_hacs_repo.SCREENSHOTS), ("rc11", publish_hacs_repo.SCREENSHOTS[:3]),
                                  ("beta18", publish_hacs_repo.SCREENSHOTS)):
                for name in names:
                    (Path(tmp) / f"{name}-{suffix}.png").write_bytes(b"x")
            self.assertEqual(publish_hacs_repo.screenshot_sets(tmp), ["beta18", "rc2", "rc4", "rc10"])


class CoAuthorTest(unittest.TestCase):
    def test_trailer_only_when_given_and_well_formed(self):
        self.assertEqual(publish_hacs_repo.co_author_trailer(None), "")
        self.assertEqual(publish_hacs_repo.co_author_trailer(""), "")
        self.assertEqual(publish_hacs_repo.co_author_trailer(" A B <a@b.example> "), "\n\nCo-Authored-By: A B <a@b.example>")
        for bad in ("Just a name", "<a@b.example>", "A <not an address>", "A <a@b.example>\nSigned-off-by: x"):
            with self.assertRaises(SystemExit):
                publish_hacs_repo.co_author_trailer(bad)

    def test_no_session_is_written_in_the_script(self):
        self.assertNotIn("Co-Authored-By: Claude", Path(publish_hacs_repo.__file__).read_text(encoding="utf-8"))


class CloneGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_the_hacs_clone_is_accepted_in_any_spelling_of_its_origin(self):
        for number, origin in enumerate(("https://github.com/dielessen/openthermostat-ha.git",
                                         "https://github.com/dielessen/openthermostat-ha",
                                         "https://GitHub.com/dielessen/openthermostat-ha/")):
            publish_hacs_repo.check_clone(make_clone(self.root / f"ok{number}", origin))

    def test_another_origin_is_refused_before_anything_is_written(self):
        for number, origin in enumerate(("https://github.com/dielessen/open_thermostat.git",
                                         "https://github.com/someone/openthermostat-ha.git",
                                         "git@github.com:dielessen/open_thermostat.git")):
            repo = make_clone(self.root / f"wrong{number}", origin)
            with self.assertRaisesRegex(SystemExit, "not the HACS repository clone"):
                publish_hacs_repo.check_clone(repo)
            with self.assertRaises(SystemExit):
                publish_hacs_repo.readme_only(repo, False, "", "1.0.0rc5", "rc4")
            self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "old\n")

    def test_a_clone_without_origin_is_refused(self):
        repo = self.root / "bare"
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        with self.assertRaisesRegex(SystemExit, "no origin"):
            publish_hacs_repo.check_clone(repo)

    def test_a_project_worktree_is_refused_even_with_the_right_origin(self):
        repo = make_clone(self.root / "project")
        (repo / "platformio.ini").write_text("[env]\n", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "main project"):
            publish_hacs_repo.check_clone(repo)
        with self.assertRaisesRegex(SystemExit, "main project"):
            publish_hacs_repo.readme_only(repo, False, "", "1.0.0rc5", "rc4")
        self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "old\n")

    def test_branch_and_uncommitted_changes_are_checked(self):
        repo = make_clone(self.root / "dirty")
        (repo / "README.md").write_text("edited\n", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "uncommitted"):
            publish_hacs_repo.check_clone(repo)
        git(repo, "checkout", "-q", "--", "README.md")
        git(repo, "checkout", "-q", "-b", "other")
        with self.assertRaisesRegex(SystemExit, "main branch"):
            publish_hacs_repo.check_clone(repo)


class PublishTest(unittest.TestCase):
    VERSION = "1.0.0rc5"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.environ.update(GIT_ENV)
        self.addCleanup(lambda: [os.environ.pop(key, None) for key in GIT_ENV])
        self.zip = package(self.VERSION)
        digest = hashlib.sha256(self.zip).hexdigest()
        self.files = {f"OpenThermostat-HA-{self.VERSION}.zip": self.zip,
                      "HA-SHA256SUMS.txt": f"{digest}  OpenThermostat-HA-{self.VERSION}.zip\n".encode()}

    def download(self, url):
        return self.files[url.rsplit("/", 1)[1]]

    def publish(self, repo, trailer="", **kw):
        publish_hacs_repo.publish(self.VERSION, repo, False, trailer, screenshots="rc4", download=self.download, **kw)

    def test_a_new_folder_gets_the_package_the_front_page_and_a_tag(self):
        repo = self.root / "clone"
        self.publish(repo)
        self.assertEqual(git(repo, "remote", "get-url", "origin"), publish_hacs_repo.HACS_REMOTE)
        self.assertEqual(git(repo, "tag", "--list"), self.VERSION)
        self.assertTrue((repo / "custom_components/open_thermostat/__init__.py").exists())
        self.assertFalse((repo / "notices").exists())
        self.assertIn("(such as `1.0.0rc5`)", (repo / "README.md").read_text(encoding="utf-8"))
        message = git(repo, "log", "-1", "--format=%B")
        self.assertIn(f"OpenThermostat {self.VERSION} (ha-v{self.VERSION}, package SHA-256 ", message)
        self.assertNotIn("Co-Authored-By", message)

    def test_the_trailer_comes_from_the_caller(self):
        repo = self.root / "clone"
        self.publish(repo, publish_hacs_repo.co_author_trailer("Some Session <session@example.invalid>"))
        self.assertTrue(git(repo, "log", "-1", "--format=%B").endswith(TRAILER))

    def test_a_second_run_changes_nothing(self):
        repo = self.root / "clone"
        self.publish(repo)
        head = git(repo, "rev-parse", "HEAD")
        self.publish(repo)
        self.assertEqual(git(repo, "rev-parse", "HEAD"), head)
        self.assertEqual(git(repo, "tag", "--list"), self.VERSION)

    def test_wrong_checksum_version_or_folder_stop_before_anything_is_written(self):
        repo = self.root / "clone"
        self.files["HA-SHA256SUMS.txt"] = ("0" * 64 + f"  OpenThermostat-HA-{self.VERSION}.zip\n").encode()
        with self.assertRaisesRegex(SystemExit, "does not match HA-SHA256SUMS"):
            self.publish(repo)
        self.assertFalse(repo.exists())
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "something.txt").write_text("x", encoding="utf-8")
        self.files["HA-SHA256SUMS.txt"] = f"{hashlib.sha256(self.zip).hexdigest()}  OpenThermostat-HA-{self.VERSION}.zip\n".encode()
        with self.assertRaisesRegex(SystemExit, "not a clone"):
            self.publish(occupied)
        self.assertEqual([p.name for p in occupied.iterdir()], ["something.txt"])
        foreign = make_clone(self.root / "foreign", "https://github.com/dielessen/open_thermostat.git")
        with self.assertRaises(SystemExit):
            self.publish(foreign)
        self.assertEqual((foreign / "README.md").read_text(encoding="utf-8"), "old\n")

    def test_readme_only_takes_the_version_from_the_clone_and_is_idempotent(self):
        repo = self.root / "clone"
        self.publish(repo)
        (repo / "README.md").write_text("changed on the web\n", encoding="utf-8")
        git(repo, "commit", "-q", "-am", "web edit")
        publish_hacs_repo.readme_only(repo, False, publish_hacs_repo.co_author_trailer("Some Session <session@example.invalid>"),
                                      screenshots="rc4")
        self.assertIn("(such as `1.0.0rc5`)", (repo / "README.md").read_text(encoding="utf-8"))
        self.assertTrue(git(repo, "log", "-1", "--format=%B").startswith("README: refresh the front page"))
        self.assertTrue(git(repo, "log", "-1", "--format=%B").endswith(TRAILER))
        head = git(repo, "rev-parse", "HEAD")
        publish_hacs_repo.readme_only(repo, False, "", screenshots="rc4")
        self.assertEqual(git(repo, "rev-parse", "HEAD"), head)


if __name__ == "__main__":
    unittest.main()
