import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from tickets import Handler, list_tickets

class HttpCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%s/tickets" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, query=""):
        with urlopen(self.url + query) as result:
            return json.load(result)

class ApiTests(HttpCase):
    def test_unfiltered_pages(self):
        self.assertEqual([t["id"] for t in self.get()["items"]], [1, 2])
        self.assertEqual([t["id"] for t in self.get("?page=2")["items"]], [3, 4])

    def test_filter_without_page_boundary(self):
        self.assertEqual([t["id"] for t in self.get("?owner=ada&page_size=100")["items"]], [2, 3, 5, 6])

    def test_empty_and_out_of_range(self):
        self.assertEqual(self.get("?owner=nobody")["total"], 0)
        self.assertEqual(self.get("?page=100")["items"], [])

    def test_errors(self):
        for query in ("?page=0", "?page=-1", "?page=1.5", "?page_size=101", "?status=invalid", "?unknown=x", "?page=1&page=2"):
            with self.subTest(query=query), self.assertRaises(HTTPError) as raised:
                self.get(query)
            self.assertEqual(raised.exception.code, 400)

    def test_repeat_is_stable(self):
        self.assertEqual(self.get("?owner=ada&page_size=100"), self.get("?owner=ada&page_size=100"))

    def test_repeated_filters_are_rejected(self):
        for query in ("?owner=ada&owner=bob", "?status=open&status=closed"):
            with self.subTest(query=query):
                with self.assertRaises(HTTPError) as raised:
                    self.get(query)
                self.assertEqual(raised.exception.code, 400)
                self.assertEqual(json.load(raised.exception)["error"], "unknown or repeated parameter")

    def test_direct_invalid_types(self):
        for value in (True, None, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                list_tickets(page=value)
