"""
Cislunar regime — fetch LRO/CRaTER daily dose-rate from the UNH legacy
HTML table.

Source: https://crater-products.sr.unh.edu/data/inst/dose/table_l30drate.php
Type:   Single HTML page with a one-row-per-day table. As of the
        publication-quality CRaTER L30 product, the table covers:
            **2009-06-26 → 2012-12-31  (1,285 daily records)**

This is the UNH "legacy" L30 product. Post-2012 daily-dose-rate ingests
are not exposed on the public UNH endpoint; the CRaTER team's newer
products are accessible only via direct collaboration or via PDS-PPI
under `LROCRA_2*` collection IDs — those PDS IDs returned 404 at the
time of this benchmark (2026-06). The post-2012 thread is therefore
documented as a deferred Phase II ingest, not a benchmark failure.

The 2009-2012 window covers DEEP solar minimum (cycle 24 ramp-up), which
produces the strongest GCR signal of the modern era. This is scientifically
valuable: GCR access to cislunar space is at its maximum, providing a
high-SNR baseline that distinguishes the cislunar GCR-modulation signal
from event-driven SEP contributions.

Columns (per detector D1..D6 silicon detectors in CRaTER's six-fold stack):
    raw and lunar-shadow-corrected dose-rates in mGy_Si / day.

Output: raw/crater_l30_daily.jsonl  one record per (date, detector):
    {"date": "YYYY-MM-DD", "detector": "D1", "dose_rate_raw_mgy_d":  ...,
     "dose_rate_corrected_mgy_d": ...}

Reproduce: python3 fetch_crater.py
"""

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

RAW = Path(__file__).parent / "raw"
RAW.mkdir(parents=True, exist_ok=True)
URL = "https://crater-products.sr.unh.edu/data/inst/dose/table_l30drate.php"
OUT_HTML = RAW / "crater_l30_table.html"
OUT_JSONL = RAW / "crater_l30_daily.jsonl"


class TableParser(HTMLParser):
    """Lightweight HTML table parser — picks up <tr><td>...</td></tr> rows."""

    def __init__(self):
        super().__init__()
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.row = []
        self.cell = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_row = True
            self.row = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False
        elif tag == "td" and self.in_cell:
            self.row.append("".join(self.cell).strip())
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def fetch_table():
    print(f"fetching {URL}")
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    OUT_HTML.write_bytes(r.content)
    print(f"  {len(r.content):,} bytes → {OUT_HTML.name}")
    return r.text


def parse_table(html: str):
    p = TableParser()
    p.feed(html)
    return p.rows


def main():
    html = fetch_table()
    rows = parse_table(html)
    print(f"parsed {len(rows)} rows from HTML table")

    # Expected columns (per HTML header inspection):
    #  0: Date "YYYY-MM-DD"
    #  1: Year-DOY  "YYYY-DOY"
    #  2: D1 raw   3: D2 raw  4: D3 raw  5: D4 raw  6: D5 raw  7: D6 raw
    #  8: D1 corrected ... 13: D6 corrected
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    detectors = ["D1", "D2", "D3", "D4", "D5", "D6"]
    n_records = 0
    n_dates = 0
    with OUT_JSONL.open("w") as f:
        for row in rows:
            if len(row) < 14:
                continue
            if not date_re.match(row[0]):
                continue
            date = row[0]
            n_dates += 1
            for j, det in enumerate(detectors):
                raw_str = row[2 + j].strip().replace(",", "")
                corr_str = row[8 + j].strip().replace(",", "")
                try:
                    raw = float(raw_str) if raw_str else None
                    corr = float(corr_str) if corr_str else None
                except ValueError:
                    raw, corr = None, None
                f.write(json.dumps({
                    "date": date,
                    "detector": det,
                    "dose_rate_raw_mgy_d": raw,
                    "dose_rate_corrected_mgy_d": corr,
                    "source": "UNH_CRaTER_L30_legacy",
                }) + "\n")
                n_records += 1

    print(f"wrote {OUT_JSONL.name}  ({n_records:,} records over {n_dates:,} unique dates)")
    if n_dates:
        # Show coverage
        dates = sorted({
            json.loads(line)["date"]
            for line in OUT_JSONL.read_text().splitlines()
        })
        print(f"  coverage: {dates[0]} → {dates[-1]}  ({len(dates)} unique dates)")

    print()
    print("NOTE: The UNH L30 product covers 2009-06-26 → 2012-12-31 only.")
    print("      Post-2012 CRaTER ingests require direct UNH collaboration or")
    print("      a working PDS-PPI LROCRA_2* collection (currently 404).")
    print("      This window covers deep solar minimum / cycle-24 onset — the")
    print("      strongest sustained GCR signal of the modern era.")


if __name__ == "__main__":
    main()
