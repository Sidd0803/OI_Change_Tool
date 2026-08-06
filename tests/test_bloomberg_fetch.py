import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bloomberg_fetch import all_oi_zero
# parse_expiry/is_expired live in expiry.py, the single home for the
# expired-contracts rule; bloomberg_fetch now returns Bloomberg's values
# unmodified and the zeroing happens downstream.
from expiry import is_expired, parse_expiry


# The session the reported bug came from: MU Aug3rd traded 8/3, report run 8/4.
RUN_DATE = datetime.date(2026, 8, 4)


class TestParseExpiry(unittest.TestCase):
    def test_two_digit_year(self):
        self.assertEqual(parse_expiry('MU US 8/3/26 P825 Equity'),
                         datetime.date(2026, 8, 3))

    def test_four_digit_year(self):
        self.assertEqual(parse_expiry('MU US 8/3/2026 P825 Equity'),
                         datetime.date(2026, 8, 3))

    def test_decimal_strike_is_not_mistaken_for_a_date(self):
        self.assertEqual(parse_expiry('AAPL US 12/18/26 C347.50 Equity'),
                         datetime.date(2026, 12, 18))

    def test_security_without_a_date(self):
        self.assertIsNone(parse_expiry('MU US Equity'))

    def test_impossible_date(self):
        self.assertIsNone(parse_expiry('MU US 2/31/26 P825 Equity'))


class TestIsExpired(unittest.TestCase):
    def test_yesterdays_expiry_is_expired(self):
        self.assertTrue(is_expired('MU US 8/3/26 P825 Equity', RUN_DATE))

    def test_expiring_today_is_not_expired(self):
        """An option expiring today still trades through the session."""
        self.assertFalse(is_expired('MU US 8/4/26 P825 Equity', RUN_DATE))

    def test_future_expiry_is_not_expired(self):
        self.assertFalse(is_expired('MU US 8/21/26 P930 Equity', RUN_DATE))

    def test_leap_day_expiry(self):
        self.assertTrue(is_expired('AAPL US 2/29/28 C150 Equity',
                                   datetime.date(2028, 3, 1)))

    def test_non_option_security_is_never_expired(self):
        self.assertFalse(is_expired('MU US Equity', RUN_DATE))

    def test_ticker_containing_a_slash(self):
        """BRK/B and friends must not confuse the expiry match."""
        self.assertTrue(is_expired('BRK/B US 8/3/26 C500 Equity', RUN_DATE))
        self.assertFalse(is_expired('BRK/B US 9/18/26 C500 Equity', RUN_DATE))


class TestZeroingLeavesOtherStructuresAlone(unittest.TestCase):
    """
    Zeroing keys off nothing but the leg's own expiry, so multi-leg structures
    are only touched where a leg is genuinely dead.
    """

    def test_vertical_spread_both_legs_live(self):
        legs = ['AAPL US 9/18/26 C340 Equity', 'AAPL US 9/18/26 C350 Equity']
        self.assertEqual([is_expired(s, RUN_DATE) for s in legs], [False, False])

    def test_calendar_spread_only_the_dead_leg(self):
        legs = ['MU US 8/3/26 P825 Equity', 'MU US 8/21/26 P825 Equity']
        self.assertEqual([is_expired(s, RUN_DATE) for s in legs], [True, False])

    def test_strangle_both_legs_live(self):
        legs = ['NVDA US 12/18/26 P150 Equity', 'NVDA US 12/18/26 C200 Equity']
        self.assertEqual([is_expired(s, RUN_DATE) for s in legs], [False, False])


class TestAllOiZero(unittest.TestCase):
    """
    A row of zeros from Bloomberg looks identical to a real result. It usually
    means the report was run after the close, before that session's open
    interest was published.
    """

    def test_all_zero_is_flagged(self):
        self.assertTrue(all_oi_zero({
            'AES US 8/21/26 P16 Equity': ('0', '1168'),
            'BHF US 8/21/26 P60 Equity': ('0', '630'),
            'KVUE US 9/18/26 C18 Equity': ('0', '422'),
        }))

    def test_one_real_value_is_not_flagged(self):
        self.assertFalse(all_oi_zero({
            'AES US 8/21/26 P16 Equity': ('0', '1168'),
            'BHF US 8/21/26 P60 Equity': ('-180', '630'),
        }))

    def test_negative_values_are_not_zero(self):
        self.assertFalse(all_oi_zero({
            'A US 8/21/26 P1 Equity': ('-1', '10'),
            'B US 8/21/26 P1 Equity': ('-2', '20'),
        }))

    def test_missing_values_are_not_treated_as_zero(self):
        # '' means the field was unavailable, which already warns separately.
        self.assertFalse(all_oi_zero({
            'A US 8/21/26 P1 Equity': ('', '10'),
            'B US 8/21/26 P1 Equity': ('', '20'),
        }))

    def test_single_security_is_not_enough_to_conclude(self):
        # One contract genuinely unchanged on the day is unremarkable.
        self.assertFalse(all_oi_zero({'A US 8/21/26 P1 Equity': ('0', '10')}))

    def test_empty_response(self):
        self.assertFalse(all_oi_zero({}))


if __name__ == '__main__':
    unittest.main()
