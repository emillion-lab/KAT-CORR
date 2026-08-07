"""Fetch UK STATS19 daily accident counts + London weather, run the same tests
we ran on the Bulgarian MVR data.

Prediction registered in advance:
  - autocorrelation SHOULD replicate (r roughly 0.2-0.3)
  - lunar signal should NOT replicate, and phase should not match BG
"""
import urllib.request, io, json, csv, datetime, sys

def get(url, timeout=600):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()

CANDIDATES = [
 "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-last-5-years.csv",
 "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2023.csv",
 "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-accident-last-5-years.csv",
 "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-accident-1979-2022.csv",
]

raw = None
for url in CANDIDATES:
    try:
        print("trying", url)
        raw = get(url)
        print("  got", len(raw), "bytes")
        break
    except Exception as ex:
        print("  failed:", ex)

if raw is None:
    print("FATAL: no STATS19 source reachable")
    sys.exit(1)

text = raw.decode('utf-8', 'replace')
rdr = csv.DictReader(io.StringIO(text))
fields = rdr.fieldnames
print("columns:", fields[:20])

datecol = next((c for c in fields if c.lower() == 'date'), None)
sevcol = next((c for c in fields if 'severity' in c.lower()), None)
print("datecol:", datecol, "sevcol:", sevcol)
if datecol is None:
    print("FATAL: no date column"); sys.exit(1)

daily = {}
for row in rdr:
    ds = (row.get(datecol) or '').strip()
    if not ds:
        continue
    d = None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y'):
        try:
            d = datetime.datetime.strptime(ds, fmt).date(); break
        except ValueError:
            pass
    if d is None:
        continue
    rec = daily.setdefault(d.isoformat(), {'n': 0, 'fatal': 0, 'serious': 0})
    rec['n'] += 1
    sv = (row.get(sevcol) or '').strip() if sevcol else ''
    if sv == '1':
        rec['fatal'] += 1
    elif sv == '2':
        rec['serious'] += 1

rows = sorted(daily.items())
print("days:", len(rows), "range", rows[0][0], "..", rows[-1][0])

with open('uk_accidents_daily.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['date', 'total', 'fatal', 'serious'])
    for d, r in rows:
        w.writerow([d, r['n'], r['fatal'], r['serious']])

start, end = rows[0][0], rows[-1][0]
wx_url = ('https://archive-api.open-meteo.com/v1/archive?latitude=51.5072&longitude=-0.1276'
          '&start_date=%s&end_date=%s'
          '&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,'
          'surface_pressure_mean,precipitation_sum,snowfall_sum,'
          'wind_speed_10m_max,sunshine_duration,daylight_duration'
          '&timezone=Europe%%2FLondon' % (start, end))
wj = json.loads(get(wx_url))
dd = wj['daily']
cols = ['temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean',
        'surface_pressure_mean', 'precipitation_sum', 'snowfall_sum',
        'wind_speed_10m_max', 'sunshine_duration', 'daylight_duration']
with open('uk_env.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['date'] + cols)
    for i, t in enumerate(dd['time']):
        w.writerow([t] + [dd[c][i] if dd[c][i] is not None else '' for c in cols])
print("weather days:", len(dd['time']))
print("OK: uk_accidents_daily.csv + uk_env.csv written")
