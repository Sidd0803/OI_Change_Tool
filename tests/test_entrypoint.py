"""
The pipeline can be run two ways: run_pipeline.py end to end, or each step on
its own so the clerk can edit template.txt in between. These tests cover the
guards that keep the second mode safe.
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
from entrypoint import require_input, check_alignment

# Every module the clerk may invoke directly.
STEP_SCRIPTS = [
    'template.py',
    'bloomberg_tickers.py',
    'generate_recap_input_txt.py',
    'generate_final_output.py',
    'occ_flex.py',
    'run_pipeline.py',
]


class TestStepScriptsAreCallable(unittest.TestCase):
    """Each step must be runnable on its own, not refuse."""

    def test_each_step_script_has_a_working_cli(self):
        for script in STEP_SCRIPTS:
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, script, '--help'],
                                        cwd=SRC, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0,
                                 f"{script} --help failed: {result.stderr[:400]}")
                self.assertIn('usage', result.stdout.lower())

    def test_downstream_steps_do_not_rebuild_the_template(self):
        # The clerk's edits to template.txt must survive a standalone step, so
        # no downstream script may regenerate it.
        for script in ('bloomberg_tickers.py', 'generate_recap_input_txt.py',
                       'generate_final_output.py'):
            with self.subTest(script=script):
                with open(os.path.join(SRC, script)) as f:
                    source = f.read()
                self.assertNotIn('template.template(', source)


class TestAlignmentGuard(unittest.TestCase):
    """
    OI values are positional. If template.txt is reordered without rebuilding
    bloomberg_tickers.txt, values would land on the wrong trades.
    """

    def test_matching_order_passes(self):
        pairs = [('AAPL', 2), ('MSFT', 1)]
        check_alignment(pairs, list(pairs), 'x.txt')  # must not raise

    def test_reordered_tickers_abort(self):
        with self.assertRaises(SystemExit) as ctx:
            check_alignment([('AAPL', 2), ('MSFT', 1)],
                            [('MSFT', 1), ('AAPL', 2)], 'x.txt')
        self.assertEqual(ctx.exception.code, 3)

    def test_changed_counts_abort(self):
        with self.assertRaises(SystemExit):
            check_alignment([('AAPL', 3)], [('AAPL', 2)], 'x.txt')

    def test_extra_ticker_aborts(self):
        with self.assertRaises(SystemExit):
            check_alignment([('AAPL', 1)], [('AAPL', 1), ('MSFT', 1)], 'x.txt')


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
