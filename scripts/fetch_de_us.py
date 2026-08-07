"""Probe German Unfallatlas for a usable day-of-month field; fall back to
US FARS (fatal crashes, exact dates, fully open) as the third country.

Germany is the preferred test of the "stricter reporting -> stronger pulse"
hypothesis, but Destatis strips day-of-month for privacy. Verify, don't assume.

FARS is fatal-only, which suits the current question: does the regime term
predict DEATHS in a third country?
"""
import urllib.request, io, json, csv, datetime, sys, zipfile

def get(url, timeout=900):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()

# --------------------------------------------------------------- GERMANY
DE = [
 ("2023", "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/Unfallorte2023_EPSG25832_CSV.zip"),
 ("2023b","https://unfallatlas.statistikportal.de/files/Unfallorte2023_EPSG25832_CSV.zip"),
 ("2022", "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/Unfallorte2022_EPSG25832_CSV.zip"),
]
print("=== GERMANY: probing Unfallatlas for day-of-month ===")
de_ok = False
for tag, url in DE:
    try:
        print("trying", url)
        raw = get(url)
        print("  got", len(raw), "bytes")
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in z.namelist() if n.lower().endswith('.csv')]
        print("  csv members:", names[:5])
        if not names:
            continue
        with z.open(names[0]) as fh:
            head = fh.read(4000).decode('utf-8', 'replace')
        first = head.splitlines()[0]
        cols = [c.strip().strip('"') for c in first.split(';')]
        if len(cols) < 3:
            cols = [c.strip().strip('"') for c in first.split(',')]
        print("  columns:", cols)
        has_day = any(c.upper() in ('UTAG', 'TAG', 'DAY', 'UDAY') for c in cols)
        print("  DAY-OF-MONTH PRESENT:", has_day)
        if has_day:
            de_ok = True
        else:
            print("  -> Germany unusable for daily analysis (privacy aggregation)")
        break
    except Exception as ex:
        print("  failed:", ex)

# ------------------------------------------------------------------ FARS
print()
print("=== US FARS: fatal crashes with exact dates ===")
def try_fars():
    counts = {}
    got = 0
    for yr in (2019, 2020, 2021, 2022, 2023):
        for url in ("https://static.nhtsa.gov/nhtsa/downloads/FARS/%d/National/FARS%dNationalCSV.zip" % (yr, yr),
                    "https://static.nhtsa.gov/nhtsa/downloads/FARS/%d/National/FARS%dNationalAuxiliaryCSV.zip" % (yr, yr)):
            try:
                raw = get(url)
                z = zipfile.ZipFile(io.BytesIO(raw))
                member = next((n for n in z.namelist()
                               if n.lower().split('/')[-1] in ('accident.csv', 'accident.CSV'.lower())), None)
                if member is None:
                    continue
                with z.open(member) as fh:
                    txt = fh.read().decode('utf-8', 'replace')
                rdr = csv.DictReader(io.StringIO(txt))
                fn = {c.upper(): c for c in (rdr.fieldnames or [])}
                dcol = fn.get('DAY'); mcol = fn.get('MONTH'); ycol = fn.get('YEAR')
                if not (dcol and mcol):
                    print("  %d: missing DAY/MONTH, cols=%s" % (yr, list(fn)[:12]))
                    break
                n = 0
                for row in rdr:
                    try:
                        yy = int(row[ycol]) if ycol else yr
                        d = datetime.date(yy, int(row[mcol]), int(row[dcol]))
                    except Exception:
                        continue
                    counts[d.isoformat()] = counts.get(d.isoformat(), 0) + 1
                    n += 1
                print("  FARS %d: %d fatal crashes" % (yr, n))
                got += 1
                break
            except Exception as ex:
                print("  FARS %d failed: %s" % (yr, ex))
    return counts, got

counts, got = try_fars()
if got:
    rows = sorted(counts.items())
    with open('us_accidents_daily.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date', 'total'])
        for d, n in rows:
            w.writerow([d, n])
    print("  US: %d days, %s .. %s" % (len(rows), rows[0][0], rows[-1][0]))
    # weather: continental-US centroid is meaningless; use it only as a placeholder
    url = ('https://archive-api.open-meteo.com/v1/archive?latitude=39.8283&longitude=-98.5795'
           '&start_date=%s&end_date=%s'
           '&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,'
           'surface_pressure_mean,precipitation_sum,snowfall_sum,'
           'wind_speed_10m_max,sunshine_duration,daylight_duration'
           '&timezone=America%%2FChicago' % (rows[0][0], rows[-1][0]))
    dd = json.loads(get(url))['daily']
    cols = ['temperature_2m_max','temperature_2m_min','temperature_2m_mean',
            'surface_pressure_mean','precipitation_sum','snowfall_sum',
            'wind_speed_10m_max','sunshine_duration','daylight_duration']
    with open('us_env.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date'] + cols)
        for i, t in enumerate(dd['time']):
            w.writerow([t] + [dd[c][i] if dd[c][i] is not None else '' for c in cols])
    print("  US weather rows:", len(dd['time']))
else:
    print("  FARS unavailable")

print()
print("SUMMARY: germany_daily_usable=%s  us_fars=%s" % (de_ok, bool(got)))
