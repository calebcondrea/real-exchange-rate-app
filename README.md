# IMF exchange rate explorer

A Streamlit app for monthly bilateral nominal and CPI-adjusted exchange rates, compatible with Python 3.12.

## Run

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Select two economies and the inclusive start and end months, choose a chart, and download the sample as CSV. Internet access to `api.imf.org` is required. No API key is embedded. If the IMF requires authentication or its API changes, requests will display an error; consult https://data.imf.org/en/Resource-Pages/IMF-API for current access instructions.

## Data and interpretation

The app queries IMF SDMX 3.0, IMF.STA dataflows CPI and ER, using `{country}.CPI._T.IX.M` and `{country}.XDC_USD.PA_RT.M` respectively. These are monthly CPI index and period-average domestic-currency-per-USD rates. Latest versions are requested; exact endpoint and response compatibility should be verified with the live IMF service. The country list attempts IMF CPI metadata and falls back to an ISO country list plus G163 (Euro area) when metadata cannot be read. The fallback may include countries for which IMF data are unavailable, and may omit non-ISO IMF economies.

E1 and E2 are the local currencies per USD. S = E2/E1 is units of country 2 currency per unit of country 1 currency. US dollar E = 1. RER = S × P1/P2. The real index divides RER by its arithmetic mean over valid months in the current selected sample and multiplies by 100. The index is relative to the selected sample, not a measure of a currency's absolute fair value. Changing the sample changes the baseline.

A ratio of monthly average rates is not generally the same as an average of daily cross rates. CPI series may have different base years, which affect the level of RER but cancel in the normalized index when bases are consistent through the sample. Historical currency changes, redenominations, euro adoption, and IMF revisions can introduce discontinuities. No attempt is made to splice currencies or infer missing values. Data may be missing or unavailable before 1976 or for some economies; this app starts in January 1976 and leaves gaps blank. CSV includes all months of the chosen period and the sample mean.

## Checks

For E1 = 2, E2 = 3, P1 = 120 and P2 = 100, S = 1.5 and RER = 1.8. For valid RER observations of 1.8 and 2.2, the mean is 2 and the indexes are 90 and 110; changing the range to just the first month yields an index of 100.

The calculation code was checked with synthetic data and the app was syntax-compiled. Live IMF access could not be tested from the creation environment, so API compatibility, availability, and country metadata parsing require verification on a network that can reach the IMF.
