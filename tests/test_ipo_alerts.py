from scraper.scrape_ipo import extract_ipo_rows_from_html


HTML_SAMPLE = """
<html>
  <body>
    <table>
      <tr><th>Company</th><th>Symbol</th><th>Open Date</th><th>Close Date</th><th>Shares Offered</th><th>Type</th></tr>
      <tr>
        <td>Hydropower Development</td>
        <td>HPL</td>
        <td>2026-09-15</td>
        <td>2026-09-21</td>
        <td>1200000</td>
        <td>Ordinary</td>
      </tr>
      <tr>
        <td>Local Finance</td>
        <td>LFIN</td>
        <td>2026-09-12</td>
        <td>2026-09-18</td>
        <td>900000</td>
        <td>Local</td>
      </tr>
    </table>
  </body>
</html>
"""


def test_extract_ipo_rows_from_html():
    rows = extract_ipo_rows_from_html(HTML_SAMPLE)
    assert len(rows) == 2
    assert rows[0]["company_name"] == "Hydropower Development"
    assert rows[0]["symbol"] == "HPL"
    assert rows[0]["share_type"] == "ordinary"
    assert rows[0]["shares_offered"] == 1200000
    assert rows[1]["share_type"] == "local"
