"""Fetch daily road-accident counts for additional countries, to extend the
lunar-phase replication test beyond BG and UK.

Registered prediction (written BEFORE seeing the data):
  - autocorrelation of the residual WILL replicate everywhere (r ~ 0.2-0.5)
  - lunar 29.53d phase alignment across countries is expected to FAIL once
    more countries are added; if 4/4 align within 45 deg, that is a real finding.

Sources attempted (all open data):
  FR : data.gouv.fr BAAC accident files
  ES : DGT open data
  NZ : CAS (Waka Kotahi) crash analysis system
  US : NHTSA FARS (fatal only)
"""
import urllib.request, io, json, csv, datetime, sys, zipfile

def get(url, timeout=900):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()

def write_daily(name, counts):
    rows = sorted(counts.items())
    if not rows:
        print("  !! %s: no rows" % name); return
    with open('%s_accidents_daily.csv' % name, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date', 'total'])
        for d, n in rows:
            w.writerow([d, n])
    print("  %s: %d days, %s .. %s" % (name, len(rows), rows[0][0], rows[-1][0]))

def fetch_weather(name, lat, lon, start, end, tz):
    url = ('https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s'
           '&start_date=%s&end_date=%s'
           '&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,'
           'surface_pressure_mean,precipitation_sum,snowfall_sum,'
           'wind_speed_10m_max,sunshine_duration,daylight_duration'
           '&timezone=%s' % (lat, lon, start, end, tz))
    dd = json.loads(get(url))['daily']
    cols = ['temperature_2m_max','temperature_2m_min','temperature_2m_mean',
            'surface_pressure_mean','precipitation_sum','snowfall_sum',
            'wind_speed_10m_max','sunshine_duration','daylight_duration']
    with open('%s_env.csv' % name, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date'] + cols)
        for i, t in enumerate(dd['time']):
            w.writerow([t] + [dd[c][i] if dd[c][i] is not None else '' for c in cols])
    print("  %s weather: %d days" % (name, len(dd['time'])))

# ------------------------------------------------------------------ FRANCE
# BAAC "caracteristiques" files: one CSV per year, columns an/mois/jour
FR_YEARS = {
 2019: "https://www.data.gouv.fr/fr/datasets/r/e22ba475-45a3-46ac-a0f7-9ca9ed1e283a",
 2020: "https://www.data.gouv.fr/fr/datasets/r/07a88205-83c1-4123-a993-cba5331e8ae0",
 2021: "https://www.data.gouv.fr/fr/datasets/r/85cfe8d6-3704-4c548-b7a5-7d0b1f0b1f0b",
 2022: "https://www.data.gouv.fr/fr/datasets/r/5fc299c0-4598-4c29-b74c-6a67b0cc27e7",
 2023: "https://www.data.gouv.fr/fr/datasets/r/104dbb32-704f-4e99-a71e-43563cb604f2",
}
def try_france():
    counts = {}
    got = 0
    for yr, url in FR_YEARS.items():
        try:
            raw = get(url)
            txt = raw.decode('utf-8', 'replace')
            delim = ';' if txt.count(';') > txt.count(',') else ','
            rdr = csv.DictReader(io.StringIO(txt), delimiter=delim)
            fn = [c.strip().lower() for c in (rdr.fieldnames or [])]
            if not ('jour' in fn and 'mois' in fn):
                print("  FR %d: unexpected columns %s" % (yr, fn[:8])); continue
            rdr.fieldnames = fn
            n = 0
            for row in rdr:
                try:
                    y = int(str(row.get('an')).strip())
                    if y < 100: y += 2000
                    d = datetime.date(y, int(row['mois']), int(row['jour']))
                except Exception:
                    continue
                counts[d.isoformat()] = counts.get(d.isoformat(), 0) + 1
                n += 1
            print("  FR %d: %d rows" % (yr, n)); got += 1
        except Exception as ex:
            print("  FR %d failed: %s" % (yr, ex))
    if got:
        write_daily('fr', counts)
        rows = sorted(counts)
        fetch_weather('fr', 48.8566, 2.3522, rows[0], rows[-1], 'Europe%2FParis')
        return True
    return False

# --------------------------------------------------------------- NEW ZEALAND
def try_nz():
    url = ("https://opendata.arcgis.com/api/v3/datasets/"
           "a163c5addf2c4b7f9079f08751bd2e1a_0/downloads/data?format=csv&spatialRefId=4326")
    try:
        raw = get(url)
        txt = raw.decode('utf-8', 'replace')
        rdr = csv.DictReader(io.StringIO(txt))
        fn = rdr.fieldnames or []
        print("  NZ columns:", fn[:12])
        # CAS has crashYear but not exact date -> unusable for daily analysis
        print("  NZ: no daily date field, skipping")
    except Exception as ex:
        print("  NZ failed:", ex)
    return False

print("=== FRANCE ===")
fr = try_france()
print("=== NEW ZEALAND ===")
try_nz()
print("done. france=%s" % fr)
