import unittest
from test_api import HttpCase

class FilterPaginationTests(HttpCase):
    def test_combined_filter_is_applied_before_page(self):
        result = self.get("?owner=ada&status=open&page=1&page_size=2")
        self.assertEqual([t["id"] for t in result["items"]], [3, 5], "filter matches must be paginated after filtering")
        self.assertEqual(result["total"], 3)

    def test_filtered_second_page_and_repeat(self):
        query = "?owner=ada&status=open&page=2&page_size=2"
        result = self.get(query)
        self.assertEqual([t["id"] for t in result["items"]], [6])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result, self.get(query))
