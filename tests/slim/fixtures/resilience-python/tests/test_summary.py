import unittest

from taskboard import count_statuses


class SummaryTests(unittest.TestCase):
    def test_counts_canonical_statuses(self):
        self.assertEqual(
            {"open": 2, "closed": 1},
            count_statuses(["open", "closed", " OPEN "]),
        )


if __name__ == "__main__":
    unittest.main()
