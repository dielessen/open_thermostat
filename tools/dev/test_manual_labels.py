"""The PDF manual names Home Assistant's menus; those names must exist in the integration's Dutch texts.

The generator (tools/dev/manual/make_pdf.py) writes every such name through ui() or named(). This test
reads those calls from the source (no reportlab needed) and looks each name up in translations/nl.json
and in the Dutch dashboard texts of dashboard.py. A menu that was renamed fails here, not in a customer's hands.
A second test builds the PDF when reportlab is installed.
"""
import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / 'ha/config/custom_components/open_thermostat'
MANUAL = ROOT / 'tools/dev/manual/make_pdf.py'
HELPERS = ('ui', 'named')


def strings(node):
    """Every string value of a loaded JSON document."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


def dashboard_texts():
    """The values of TEXT["nl"] in dashboard.py, read without importing Home Assistant."""
    tree = ast.parse((INTEGRATION / 'dashboard.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(target, 'id', None) == 'TEXT' for target in node.targets):
            for key, value in zip(node.value.keys, node.value.values):
                if getattr(key, 'value', None) == 'nl':
                    return {text for text in ast.literal_eval(value).values() if isinstance(text, str)}
    raise AssertionError('the Dutch dashboard texts (TEXT["nl"]) were not found in dashboard.py')


def manual_labels():
    """{name: line} of every name the manual gives to ui() or named()."""
    tree = ast.parse(MANUAL.read_text(encoding='utf-8'))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) in HELPERS:
            for argument in node.args:
                if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
                    raise AssertionError(f'make_pdf.py line {node.lineno}: {node.func.id}() takes plain strings only')
                found.setdefault(argument.value, node.lineno)
    return found


class ManualLabelTests(unittest.TestCase):
    def test_every_name_in_the_manual_is_shown_by_the_integration(self):
        translations = json.loads((INTEGRATION / 'translations/nl.json').read_text(encoding='utf-8'))
        known = set(strings(translations)) | dashboard_texts()
        labels = manual_labels()
        self.assertGreater(len(labels), 30, 'the manual should name its menus through ui() and named()')
        unknown = {label: f'make_pdf.py line {line}' for label, line in labels.items() if label not in known}
        self.assertEqual(unknown, {}, 'these names are not in translations/nl.json or the Dutch dashboard texts; '
                                      'the menu was renamed or the name is misspelled')

    def test_the_manual_builds_when_reportlab_is_installed(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest('reportlab is not installed (see tools/dev/manual/README.md)')
        spec = importlib.util.spec_from_file_location('make_pdf_under_test', MANUAL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'manual.pdf'
            try:
                module.main([str(target)])
            except SystemExit as stop:
                if str(stop).startswith('No usable fonts'):
                    self.skipTest(str(stop))
                raise
            data = target.read_bytes()
        self.assertTrue(data.startswith(b'%PDF'))
        self.assertGreater(len(data), 20000)


if __name__ == '__main__':
    unittest.main()
