# Simulated ticket API

Synthetic local FDE pilot. This is not Exposure-Agent or customer data.

Run: `python3 tickets.py --port 8765`
Read: `GET /tickets?owner=ada&status=open&page=1&page_size=2`
Test: `python3 -B -m unittest discover -s tests -v`

The result contains matching tickets sorted by ID, then paginated. `total` is the
number of all matches. Page and page_size are positive integers; page_size is at
most 100. Owners are arbitrary exact strings; status is open or closed. Repeated
reads are deterministic and do not change data. Invalid/unknown/repeated query
parameters return 400. The only endpoint is read-only; there is no deployment.

The baseline intentionally contains a filter-before-pagination requirement
violation. The pilot fixes only that behavior and adds its regression.
