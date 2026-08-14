import unittest

from taskboard import normalize_status, status_label


class StatusTests(unittest.TestCase):
    def test_canonical_statuses_are_normalized(self):
        self.assertEqual("open", normalize_status(" OPEN "))
        self.assertEqual("closed", normalize_status("closed"))

    def test_unknown_alias_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_status("todo")

    def test_label_uses_canonical_status(self):
        self.assertEqual("Open", status_label("open"))


if __name__ == "__main__":
    unittest.main()
