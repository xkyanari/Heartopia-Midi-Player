import importlib
import multiprocessing
import subprocess
import sys
import unittest
from unittest.mock import patch


def import_in_child(result):
    with patch("tkinter.Tk", side_effect=AssertionError("Unexpected child window")):
        module = importlib.import_module("main")
        result.put(callable(module.main) and not hasattr(module, "root"))


class EntrypointTests(unittest.TestCase):
    def test_import_does_not_create_gui_or_require_conversion_packages(self):
        # Fresh interpreter: other tests legitimately decode audio/import av.
        result = subprocess.run([sys.executable, "-c", """
import sys
from unittest.mock import patch
with patch('tkinter.Tk', side_effect=AssertionError('Unexpected window')):
    import main
assert callable(main.main) and not hasattr(main, 'root')
assert not any(name in sys.modules for name in ('torch', 'av', 'piano_transcription_inference'))
"""], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_spawned_child_import_does_not_create_gui(self):
        context = multiprocessing.get_context("spawn")
        result = context.Queue()
        child = context.Process(target=import_in_child, args=(result,))
        try:
            child.start()
            self.assertTrue(result.get(timeout=15))
            child.join(timeout=15)
            self.assertEqual(child.exitcode, 0)
        finally:
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
            result.close()
            result.join_thread()


if __name__ == "__main__":
    unittest.main()
