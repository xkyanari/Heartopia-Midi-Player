"""Runtime dependencies exclude the unrelated PyPI Tk placeholder."""
from pathlib import Path
import unittest


class RequirementsTests(unittest.TestCase):
    def test_tk_is_not_a_pip_dependency(self):
        requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
        packages = {line.strip().casefold() for line in requirements.splitlines() if line.strip()}
        self.assertNotIn("tk", packages)
        self.assertTrue({"mido", "keyboard"}.issubset(packages))
