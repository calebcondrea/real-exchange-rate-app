import io
import re
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import pycountry
import requests
import streamlit as st
from plotly.subplots import make_subplots

BASE = 'https://api.imf.org/external/sdmx/3.0'
START = '1976-01'

@st.cache_data(ttl=86400, show_spinner=False)
def country_options():
    # Metadata can include non-country aggregates; fall back to ISO names.
    fallback = {f'{c.name} ({c.alpha_3})': c.alpha_3 for c in pycountry.countries}
    fallback['Euro area (G163)'] = 'G163'
    try:
        url = f'{BASE}/structure/codelist/IMF.STA/CL_CPI_COUNTRY/~'
        r = requests.get(url, headers={'Accept': 'application/vnd.sdmx.structure+json;version=2.0.0'}, timeout=15)
        r.raise_for_status()
        data = r.json()
        lists = data.get('data', {}).get('codelists', [])
        entries = lists[0].get('codes', []) if lists else []
        names = {}
        for item in entries:
            code = item.get('id', '')
            if not (re.fullmatch(r'[A-Z]{3}', code) or code == 'G163'):
                continue
            name = item.get('name') or item.get('names', {}).get('en') or code
            if isinstance(name, dict):
                name = name.get('en', code)
            names[f'{name} ({code})'] = code
        if 'G163' not in names.values():
            names['Euro area (G163)'] = 'G163'
        if len(names) < 50:
            raise ValueError('Country metadata did not contain a usable list.')
        return dict(sorted(names.items())), False
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return dict(sorted(fallback.items())), True

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_series(code, kind):
    flow, key = ('CPI', f'{code}.CPI._T.IX.M') if kind == 'cpi' else ('ER', f'{code}.XDC_USD.PA_RT.M')
    url = f'{BASE}/data/dataflow/IMF.STA/{flow}/~/{key}'
    try:
        response = requests.get(url, headers={'Accept': 'text/csv'}, params={'c[TIME_PERIOD]': 'ge:1976-M01'}, timeout=40)
        if response.status_code in (404, 204):
            return pd.Series(dtype=float), f'No {kind.upper()} data found for {code}.'
        response.raise_for_status()
        raw = pd.read_csv(io.StringIO(response.text))
        cols = {str(c).upper(): c for c in raw.columns}
        if not {'TIME_PERIOD', 'OBS_VALUE'} <= cols.keys():
            raise ValueError('Response lacks TIME_PERIOD or OBS_VALUE columns')
        dates = pd.to_datetime(raw[cols['TIME_PERIOD']].astype(str).str.replace('-M', '-', regex=False), errors='coerce')
        values = pd.to_numeric(raw[cols['OBS_VALUE']], errors='coerce')
        df = pd.DataFrame({'date': dates, 'value': values}).dropna(subset=['date'])
        df['date'] = df['date'].dt.to_period('M').dt.to_timestamp()
        if df['date'].duplicated().any():
            raise ValueError('Multiple observations for the same month; cannot select a unique series')
        return df.set_index('date')['value'].sort_index(), None
    except (requests.RequestException, ValueError, pd.errors.ParserError) as e:
        return pd.Series(dtype=float), f'{code} {kind.upper()} request failed: {e}'

def calculate(index, p1, p2, e1, e2):
    frame = pd.DataFrame(index=index)
    for name, series in [('P1_CPI', p1), ('P2_CPI', p2), ('E1_per_USD', e1), ('E2_per_USD', e2)]:
        frame[name] = series.reindex(index)
        frame.loc[frame[name] <= 0, name] = float('nan')
    frame['S_Country2_per_Country1'] = frame.E2_per_USD / frame.E1_per_USD
    frame['RER'] = frame.S_Country2_per_Country1 * frame.P1_CPI / frame.P2_CPI
    mean = frame.RER.mean()
    frame['RER_star_sample_mean'] = mean
    frame['Real_Index'] = 100 * frame.RER / mean if pd.notna(mean) and mean > 0 else float('nan')
    frame.index.name = 'month'
    return frame, mean

def run():
    st.set_page_config(page_title='IMF Exchange Rate Explorer', layout='wide')
    st.title('Real and nominal exchange rates')
    st.caption('Monthly IMF data · Select two economies and a sample period to compare their exchange rates.')
    countries, fallback = country_options()
    if fallback:
        st.warning('IMF country metadata was unavailable. The selector uses an ISO country list plus the Euro area; some entries may have no IMF observations.')
    labels = list(countries)
    def default(code):
        return next((i for i, name in enumerate(labels) if countries[name] == code), 0)
    a, b = st.columns(2)
    c1 = a.selectbox('Country 1', labels, index=default('G163'))
    c2 = b.selectbox('Country 2', labels, index=default('USA'))
    code1, code2 = countries[c1], countries[c2]
    d1, d2 = st.columns(2)
    start = d1.date_input('Start month', value=date(1999, 1, 1), min_value=date(1976, 1, 1), max_value=date.today())
    end = d2.date_input('End month', value=date.today().replace(day=1), min_value=date(1976, 1, 1), max_value=date.today())
    start, end = pd.Timestamp(start).to_period('M').to_timestamp(), pd.Timestamp(end).to_period('M').to_timestamp()
    if start > end:
        st.error('The start month must not be after the end month.')
        return
    index = pd.date_range(start, end, freq='MS')
    with st.spinner('Retrieving IMF monthly data…'):
        p1, err1 = fetch_series(code1, 'cpi')
        p2, err2 = fetch_series(code2, 'cpi')
        if code1 == 'USA':
            e1, err3 = pd.Series(1.0, index=index), None
        else:
            e1, err3 = fetch_series(code1, 'exchange rate')
        if code2 == 'USA':
            e2, err4 = pd.Series(1.0, index=index), None
        else:
            e2, err4 = fetch_series(code2, 'exchange rate')
    for error in dict.fromkeys(x for x in [err1, err2, err3, err4] if x):
        st.warning(error)
    frame, mean = calculate(index, p1, p2, e1, e2)
    valid = frame.RER.notna().sum()
    x, y, z = st.columns(3)
    x.metric('Sample average RER', f'{mean:.4f}' if pd.notna(mean) else 'Unavailable')
    y.metric('Valid RER months', f'{valid:,} / {len(frame):,}')
    z.metric('Nominal rate', f'{code2} currency per {code1} currency')
    if valid < len(frame):
        st.info('Some months lack one or more required observations. Missing months are not filled or included in the real-rate average.')
    mode = st.radio('Chart', ['Real', 'Nominal', 'Both'], horizontal=True)
    fig = make_subplots(specs=[[{'secondary_y': mode == 'Both'}]])
    if mode in ('Real', 'Both'):
        fig.add_trace(go.Scatter(x=frame.index, y=frame.Real_Index, name='Real index', connectgaps=False), secondary_y=False)
    if mode in ('Nominal', 'Both'):
        fig.add_trace(go.Scatter(x=frame.index, y=frame.S_Country2_per_Country1, name='Nominal S', connectgaps=False), secondary_y=(mode == 'Both'))
    fig.update_xaxes(title='Month')
    fig.update_yaxes(title_text='Real index (sample average = 100)' if mode != 'Nominal' else f'{code2} currency per {code1} currency', secondary_y=False)
    if mode == 'Both':
        fig.update_yaxes(title_text=f'{code2} currency per {code1} currency', secondary_y=True)
    fig.update_layout(hovermode='x unified', legend=dict(orientation='h'))
    st.plotly_chart(fig, use_container_width=True)
    csv = frame.reset_index().assign(month=lambda x: x.month.dt.strftime('%Y-%m')).to_csv(index=False).encode('utf-8')
    st.download_button('Download selected sample as CSV', csv, 'imf_exchange_rates.csv', 'text/csv')
    with st.expander('About the calculations and data'):
        st.markdown('S = E2 / E1, where E is local currency per US dollar. RER = S × P1 / P2; the real index is 100 × RER / the average valid RER in the selected sample. Currency changes, redenominations, differing CPI base periods, and IMF data gaps can affect interpretation. Nominal S is a ratio of monthly average rates, not necessarily the monthly average of daily cross rates.')

if __name__ == '__main__':
    run()
