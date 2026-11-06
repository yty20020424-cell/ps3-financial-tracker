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
    url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}'
    df = pd.read_csv(io.BytesIO(download(url)))
    df.columns = ['date', 'value']
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    return df.dropna().sort_values('date')

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
