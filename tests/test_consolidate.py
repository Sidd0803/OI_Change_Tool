"""
The same option traded several times in a day produces one template block per
print, each carrying an identical OI Change line. consolidate.py merges those
so the recap shows the trades together under a single OI figure.
"""
import os
import sys
import tempfile
import unittest

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, 'src')
from datetime import date
from consolidate import (parse_blocks, consolidate, render, structure_key,
                         drop_expired, main)

SEP = '-' * 33


def block(descriptions, oi_lines):
    return '\n'.join(descriptions + [''] + oi_lines + [SEP]) + '\n'


REPEATED = (
    block(['MU Oct 1050 Put 1,520x traded 39.00 live; stk ref 1,063.00 - looks bot'],
          ['MU Oct 1050 Put OI Change:'])
    + block(['MU Oct 1050 Put 2k traded 39.25 elec live; stk ref 1,062.50 - looks bot'],
            ['MU Oct 1050 Put OI Change:'])
)


class TestParseBlocks(unittest.TestCase):

    def test_splits_on_separator(self):
        blocks = parse_blocks(REPEATED.splitlines(keepends=True))
        self.assertEqual(len(blocks), 2)

    def test_separates_descriptions_from_oi_lines(self):
        descriptions, oi_lines = parse_blocks(REPEATED.splitlines(keepends=True))[0]
        self.assertEqual(len(descriptions), 1)
        self.assertTrue(descriptions[0].startswith('MU Oct 1050 Put 1,520x'))
        self.assertEqual(oi_lines, ['MU Oct 1050 Put OI Change:'])

    def test_multi_leg_block(self):
        text = block(['PAYO Nov/Jan 7 CS 250x traded even mid'],
                     ['PAYO Nov 7 Call OI Change:', 'PAYO Jan 7 Call OI Change:'])
        descriptions, oi_lines = parse_blocks(text.splitlines(keepends=True))[0]
        self.assertEqual(len(oi_lines), 2)


class TestConsolidate(unittest.TestCase):

    def test_same_structure_merges(self):
        merged, groups = consolidate(parse_blocks(REPEATED.splitlines(keepends=True)))
        self.assertEqual(len(merged), 1)
        descriptions, oi_lines = merged[0]
        self.assertEqual(len(descriptions), 2)
        self.assertEqual(oi_lines, ['MU Oct 1050 Put OI Change:'])
        self.assertEqual(groups[('MU Oct 1050 Put OI Change:',)], 2)

    def test_descriptions_keep_their_order(self):
        merged, _ = consolidate(parse_blocks(REPEATED.splitlines(keepends=True)))
        descriptions = merged[0][0]
        self.assertIn('1,520x', descriptions[0])
        self.assertIn('2k', descriptions[1])

    def test_different_structures_stay_apart(self):
        text = (block(['MU Oct 1050 Put 1k traded 39.00'], ['MU Oct 1050 Put OI Change:'])
                + block(['MU Oct 1100 Put 1k traded 49.00'], ['MU Oct 1100 Put OI Change:']))
        merged, _ = consolidate(parse_blocks(text.splitlines(keepends=True)))
        self.assertEqual(len(merged), 2)

    def test_multi_leg_merges_only_on_the_full_leg_set(self):
        spread = ['PAYO Nov 7 Call OI Change:', 'PAYO Jan 7 Call OI Change:']
        text = (block(['PAYO CS 250x'], spread)
                + block(['PAYO CS 100x'], spread)
                + block(['PAYO Nov 7 Call 50x'], ['PAYO Nov 7 Call OI Change:']))
        merged, _ = consolidate(parse_blocks(text.splitlines(keepends=True)))
        self.assertEqual(len(merged), 2)
        self.assertEqual(len(merged[0][0]), 2)   # the two spreads together
        self.assertEqual(merged[1][1], ['PAYO Nov 7 Call OI Change:'])

    def test_group_lands_at_first_appearance(self):
        text = (block(['A 1x'], ['A Oct 1 Call OI Change:'])
                + block(['B 1x'], ['B Oct 1 Call OI Change:'])
                + block(['A 2x'], ['A Oct 1 Call OI Change:']))
        merged, _ = consolidate(parse_blocks(text.splitlines(keepends=True)))
        self.assertEqual([d[0][0] for d in merged], ['A 1x', 'B 1x'])
        self.assertEqual(merged[0][0], ['A 1x', 'A 2x'])

    def test_unparsed_block_is_never_folded_away(self):
        # template.py could not parse this trade — it must survive on its own
        # rather than being absorbed into a neighbour.
        text = (block(['SOMETHING ODD 1k traded'], [])
                + block(['MU Oct 1050 Put 1k traded 39.00'], ['MU Oct 1050 Put OI Change:']))
        merged, _ = consolidate(parse_blocks(text.splitlines(keepends=True)))
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0], (['SOMETHING ODD 1k traded'], []))

    def test_identical_prints_are_both_kept(self):
        # Two fills of the same size at the same price are two trades.
        line = 'MU Oct 1050 Put 1k traded 39.00'
        text = (block([line], ['MU Oct 1050 Put OI Change:'])
                + block([line], ['MU Oct 1050 Put OI Change:']))
        merged, _ = consolidate(parse_blocks(text.splitlines(keepends=True)))
        self.assertEqual(merged[0][0], [line, line])


class TestRenderRoundTrip(unittest.TestCase):

    def test_output_matches_template_layout(self):
        merged, _ = consolidate(parse_blocks(REPEATED.splitlines(keepends=True)))
        lines = [l.rstrip('\n') for l in render(merged)]
        self.assertTrue(lines[0].startswith('MU Oct 1050 Put 1,520x'))
        self.assertTrue(lines[1].startswith('MU Oct 1050 Put 2k'))
        self.assertEqual(lines[2], '')
        self.assertEqual(lines[3], 'MU Oct 1050 Put OI Change:')
        self.assertEqual(lines[4], SEP)

    def test_running_twice_changes_nothing(self):
        once = ''.join(render(consolidate(parse_blocks(
            REPEATED.splitlines(keepends=True)))[0]))
        twice = ''.join(render(consolidate(parse_blocks(
            once.splitlines(keepends=True)))[0]))
        self.assertEqual(once, twice)


class TestMainRewritesInPlace(unittest.TestCase):

    def test_in_place_rewrite(self):
        f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False,
                                        encoding='utf-8')
        f.write(REPEATED)
        f.close()
        try:
            main(f.name)
            with open(f.name, encoding='utf-8') as fh:
                text = fh.read()
            self.assertEqual(text.count('OI Change:'), 1)
            self.assertIn('1,520x', text)
            self.assertIn('2k traded', text)
        finally:
            os.unlink(f.name)

    def test_separate_output_leaves_input_alone(self):
        src = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False,
                                          encoding='utf-8')
        src.write(REPEATED)
        src.close()
        dst = os.path.join(tempfile.gettempdir(), 'consolidated_out.txt')
        try:
            main(src.name, dst)
            with open(src.name, encoding='utf-8') as fh:
                self.assertEqual(fh.read().count('OI Change:'), 2)
            with open(dst, encoding='utf-8') as fh:
                self.assertEqual(fh.read().count('OI Change:'), 1)
        finally:
            os.unlink(src.name)
            if os.path.exists(dst):
                os.unlink(dst)


class TestDropExpired(unittest.TestCase):
    """
    A contract already dead by the trading day being reported would print
    OI Change: 0, which tells the reader nothing, so the line is cut.
    Boundary is inclusive: expiring ON the trade date counts as dead.
    """

    TRADE_DATE = date(2026, 10, 1)   # dates.txt has 10/16/26 as the Oct monthly

    def test_expired_leg_is_cut_and_live_leg_kept(self):
        blocks = [(['MU Oct1st/Oct 1050 PS 1k traded'],
                   ['MU Oct1st 1050 Put OI Change:', 'MU Oct 1050 Put OI Change:'])]
        kept, cut_lines, cut_blocks = drop_expired(blocks, self.TRADE_DATE)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0][1], ['MU Oct 1050 Put OI Change:'])
        self.assertEqual(cut_lines, ['MU Oct1st 1050 Put OI Change:'])
        self.assertEqual(cut_blocks, [])

    def test_description_survives_when_a_leg_is_cut(self):
        blocks = [(['MU Oct1st/Oct 1050 PS 1k traded'],
                   ['MU Oct1st 1050 Put OI Change:', 'MU Oct 1050 Put OI Change:'])]
        kept, _, _ = drop_expired(blocks, self.TRADE_DATE)
        self.assertEqual(kept[0][0], ['MU Oct1st/Oct 1050 PS 1k traded'])

    def test_fully_expired_trade_is_dropped(self):
        blocks = [(['MU Oct1st 1050 Put 1k traded'],
                   ['MU Oct1st 1050 Put OI Change:'])]
        kept, cut_lines, cut_blocks = drop_expired(blocks, self.TRADE_DATE)
        self.assertEqual(kept, [])
        self.assertEqual(len(cut_blocks), 1)

    def test_live_trade_untouched(self):
        blocks = [(['MU Oct 1050 Put 1k traded'], ['MU Oct 1050 Put OI Change:'])]
        kept, cut_lines, cut_blocks = drop_expired(blocks, self.TRADE_DATE)
        self.assertEqual(kept, blocks)
        self.assertEqual(cut_lines, [])

    def test_expiring_on_the_trade_date_counts_as_dead(self):
        # dates.txt resolves Oct1st to 10/1/26, the trade date itself.
        blocks = [(['X'], ['MU Oct1st 1050 Put OI Change:'])]
        kept, _, _ = drop_expired(blocks, date(2026, 10, 1))
        self.assertEqual(kept, [])
        # One day earlier it was still alive.
        kept, _, _ = drop_expired(blocks, date(2026, 9, 30))
        self.assertEqual(len(kept), 1)

    def test_unresolvable_expiry_is_never_cut(self):
        blocks = [(['odd'], ['WHAT Xyz 1 Call OI Change:'])]
        kept, cut_lines, _ = drop_expired(blocks, self.TRADE_DATE)
        self.assertEqual(len(kept), 1)
        self.assertEqual(cut_lines, [])

    def test_unparsed_block_is_untouched(self):
        blocks = [(['SOMETHING ODD 1k traded'], [])]
        kept, _, _ = drop_expired(blocks, self.TRADE_DATE)
        self.assertEqual(kept, blocks)


class TestDropThenGroup(unittest.TestCase):
    """
    Two trades differing only in a leg that is now dead present as the same
    structure once it is cut, so they must end up grouped. Dropping has to
    happen before grouping for that to work.
    """

    TRADE_DATE = date(2026, 10, 2)

    def test_trades_differing_only_in_a_dead_leg_merge(self):
        text = (block(['AAPL Oct/Oct2nd 330 CS 1k traded 3.86'],
                      ['AAPL Oct 330 Call OI Change:',
                       'AAPL Oct2nd 332.5 Call OI Change:'])
                + block(['AAPL Oct/Oct2nd 330 CS 1k traded 3.22'],
                        ['AAPL Oct 330 Call OI Change:',
                         'AAPL Oct2nd 330 Call OI Change:']))
        live, cut_lines, _ = drop_expired(
            parse_blocks(text.splitlines(keepends=True)), self.TRADE_DATE)
        merged, _ = consolidate(live)

        self.assertEqual(len(cut_lines), 2)
        self.assertEqual(len(merged), 1, "dead legs cut but blocks not merged")
        descriptions, oi_lines = merged[0]
        self.assertEqual(oi_lines, ['AAPL Oct 330 Call OI Change:'])
        self.assertEqual(len(descriptions), 2)

    def test_grouping_first_would_have_missed_it(self):
        # Guards the ordering: the same input grouped first stays as two
        # blocks, because the full leg sets differ before the cut.
        text = (block(['a'], ['AAPL Oct 330 Call OI Change:',
                              'AAPL Oct2nd 332.5 Call OI Change:'])
                + block(['b'], ['AAPL Oct 330 Call OI Change:',
                                'AAPL Oct2nd 330 Call OI Change:']))
        grouped_first, _ = consolidate(parse_blocks(text.splitlines(keepends=True)))
        self.assertEqual(len(grouped_first), 2)


if __name__ == '__main__':
    unittest.main()
