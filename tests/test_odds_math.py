import unittest

from football_edge.odds_math import (american_to_decimal, expected_value, hold,
                                     implied_prob, no_vig, prob_to_american)


class OddsMathTest(unittest.TestCase):
    def test_conversions(self):
        self.assertAlmostEqual(american_to_decimal(-110), 1.9090909, places=6)
        self.assertAlmostEqual(american_to_decimal(150), 2.5)
        self.assertAlmostEqual(implied_prob(-200), 2 / 3)
        self.assertEqual(prob_to_american(0.5), -100)
        self.assertEqual(prob_to_american(0.4), 150)

    def test_no_vig(self):
        a, b = no_vig(-110, -110)
        self.assertAlmostEqual(a, 0.5)
        self.assertAlmostEqual(a + b, 1)
        self.assertAlmostEqual(hold(-110, -110), 0.047619, places=5)

    def test_ev(self):
        self.assertAlmostEqual(expected_value(0.5, 100), 0.0)
        self.assertGreater(expected_value(0.55, -110), 0)
        self.assertLess(expected_value(0.5, -110), 0)


if __name__ == "__main__":
    unittest.main()
