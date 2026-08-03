"""
original_input.txt is the single starting point for every report. These tests
lock that in: the step modules must refuse to run on their own, because doing
so would build a correct-looking report from stale intermediate files.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
os.chdir(ROOT)
SRC = os.path.join(ROOT, 'src')
sys.path.insert(0, 'src')
from entrypoint import require_input

# Every module that sits partway down the chain.
STEP_SCRIPTS = [
    'template.py',
    'bloomberg_tickers.py',
    'generate_recap_input_txt.py',
    'generate_final_output.py',
    'generate_trade_recap.py',
    'occ_flex.py',
]


class TestStepScriptsRefuseStandalone(unittest.TestCase):

    def _run(self, script):
        return subprocess.run([sys.executable, script], cwd=SRC,
                              capture_output=True, text=True)

    def test_each_step_script_exits_nonzero(self):
        for script in STEP_SCRIPTS:
            with self.subTest(script=script):
                result = self._run(script)
                self.assertNotEqual(
                    result.returncode, 0,
                    f"{script} ran standalone instead of refusing")

    def test_each_step_script_points_at_run_pipeline(self):
        for script in STEP_SCRIPTS:
            with self.subTest(script=script):
                result = self._run(script)
                self.assertIn('run_pipeline.py', result.stderr)

    def test_no_step_script_writes_output_when_refused(self):
        # A refusal must be inert — nothing regenerated, nothing touched.
        recap = os.path.join(ROOT, 'data', 'recap_input.txt')
        before = os.path.getmtime(recap)
        self._run('generate_recap_input_txt.py')
        self.assertEqual(os.path.getmtime(recap), before)


class TestRunPipelineStillRuns(unittest.TestCase):
    """The one supported entry point must not be caught by the guard."""

    def test_run_pipeline_help_works(self):
        result = subprocess.run([sys.executable, 'run_pipeline.py', '--help'],
                                cwd=SRC, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--reports', result.stdout)


class TestRequireInput(unittest.TestCase):

    def test_missing_input_raises(self):
        with self.assertRaises(FileNotFoundError):
            require_input(os.path.join(tempfile.gettempdir(), 'no_such_input.txt'))

    def test_empty_input_raises(self):
        f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False)
        f.close()
        try:
            with self.assertRaises(ValueError):
                require_input(f.name)
        finally:
            os.unlink(f.name)

    def test_populated_input_passes(self):
        f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False)
        f.write('Color - AAPL Aug 200 Call 1k traded 1.00\n')
        f.close()
        try:
            require_input(f.name)  # must not raise
        finally:
            os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
