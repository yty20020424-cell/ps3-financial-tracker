"""Download public market series and publish a static monthly dataset."""
from __future__ import annotations
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

START = '2018-01-01'
S = requests.Session()
S.headers.update({'User-Agent': 'PS3-Financial-Tracker/1.0 (student project)'})

def download(url):
    response = S.get(url, timeout=90)
    response.raise_for_status()
    return response.content

def fred(series):
    sources = {
    "DGS10": (
        "https://calcfi.app/api/rates/"
        "10-year-treasury?format=csv"
    ),
    "SP500": (
        "https://raw.githubusercontent.com/"
        "datasets/s-and-p-500/main/"
        "archive/fred_sp500.csv"
    )
}

    if series not in sources:
        raise ValueError(f"Unknown series: {series}")

    print(f"Downloading {series} from DataHub")

    response = S.get(sources[series], timeout=45)
    response.raise_for_status()

    content = response.content
    first_line = content.splitlines()[0].decode(
    "utf-8-sig", errors="replace")
    print(f"{series} CSV header: {first_line}")
    if "date" not in first_line.lower() or "," not in first_line:
    raise ValueError(
        f"{series} returned unexpected data: {first_line[:150]}"
    )
    df = pd.read_csv(io.BytesIO(content))

    df.columns = [
        str(c).strip().lower() for c in df.columns
    ]

    date_col = next(
        (c for c in df.columns if c in
         ("date", "observation_date")),
        None
    )

    value_col = next(
        (c for c in df.columns if c in
         ("value", series.lower(), "close")),
        None
    )

    if date_col is None or value_col is None:
        raise ValueError(
            f"Unexpected columns for {series}: {list(df.columns)}"
        )

    df = df[[date_col, value_col]].copy()
    df.columns = ["date", "value"]

    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )
    df["value"] = pd.to_numeric(
        df["value"], errors="coerce"
    )

    df = df.dropna().sort_values("date")
    df = df[df["date"] >= pd.Timestamp(START)]

    if df.empty:
        raise ValueError(f"No data for {series}")

    print(f"Loaded {len(df)} observations for {series}")

    return df

def acm():
    url = 'https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls'
    # The NY Fed workbook has 'ACM Monthly', with columns DATE and ACMTP10.
    frame = pd.read_excel(io.BytesIO(download(url)), sheet_name='ACM Monthly', engine='xlrd')
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    if 'DATE' not in frame or 'ACMTP10' not in frame:
        raise ValueError(f'Unexpected NY Fed workbook columns: {list(frame.columns)}')
    frame = frame[['DATE', 'ACMTP10']].rename(columns={'DATE': 'date', 'ACMTP10': 'premium'})
    frame['date'] = pd.to_datetime(frame['date'], errors='coerce')
    frame['premium'] = pd.to_numeric(frame['premium'], errors='coerce')
    return frame.dropna().sort_values('date')

def monthly(frame, col):
    frame = frame.copy()
    frame['month'] = frame['date'].dt.strftime('%Y-%m')
    return dict(frame.sort_values('date').drop_duplicates('month', keep='last')[['month', col]].itertuples(index=False, name=None))

def main():
    premium = monthly(acm(), 'premium')
    yield10 = monthly(fred('DGS10'), 'value')
    sp500 = monthly(fred('SP500'), 'value')
    # Values are paired only within the same month, never forward filled.
    months = sorted(set(premium) & set(yield10) & set(sp500))
    rows = [
        {'month': m, 'termPremium': round(float(premium[m]), 6),
         'yield10': round(float(yield10[m]), 6), 'sp500': round(float(sp500[m]), 4)}
        for m in months if m >= '2019-01'
    ]
    if len(rows) < 36:
        raise ValueError(f'Not enough common history: {len(rows)} months')
    output = {'updatedUTC': datetime.now(timezone.utc).isoformat(),
              'frequency': 'month-end/latest available within month',
              'sources': {'premium': 'https://www.newyorkfed.org/research/data_indicators/term-premia-tabs',
                          'yield': 'https://fred.stlouisfed.org/series/DGS10',
                          'stocks': 'https://fred.stlouisfed.org/series/SP500'},
              'rows': rows}
    Path('data.json').write_text(json.dumps(output, separators=(',', ':')), encoding='utf-8')
    print(f'Wrote {len(rows)} observations: {rows[0]["month"]} to {rows[-1]["month"]}')

if __name__ == '__main__':
    main()
