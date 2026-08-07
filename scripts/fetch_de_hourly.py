"""German Unfallatlas: no day-of-month, so no regime test is possible.
What it DOES have is USTUNDE (hour) on every record, across ~250k crashes/year.

Use it for the one question our daily data can never answer:
does crash risk shift within the day, and does that shift change by season?
This is the closest available test of the "afternoon fatigue / dehydration"
hypothesis, which daily totals average away completely.
"""
import urllib.request, io, csv, zipfile, sys
from collections import defaultdict

def get(url, timeout=900):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()

YEARS = [
 ("2023","https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/Unfallorte2023_EPSG25832_CSV.zip"),
 ("2022","https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/Unfallorte2022_EPSG25832_CSV.zip"),
 ("2021","https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/Unfallorte2021_EPSG25832_CSV.zip"),
]

# hour x month x weekday x severity counts
rows_out = []
for tag, url in YEARS:
    try:
        print("fetching", tag)
        raw = get(url)
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next(n for n in z.namelist() if n.lower().endswith('.csv'))
        with z.open(name) as fh:
            txt = fh.read().decode('utf-8', 'replace')
        delim = ';' if txt.count(';') > txt.count(',') else ','
        rdr = csv.DictReader(io.StringIO(txt), delimiter=delim)
        fn = {c.strip().strip('\ufeff').upper(): c for c in (rdr.fieldnames or [])}
        need = ['UJAHR','UMONAT','USTUNDE','UWOCHENTAG','UKATEGORIE']
        if not all(k in fn for k in need):
            print("  missing cols:", [k for k in need if k not in fn]); continue
        n = 0
        agg = defaultdict(lambda: [0,0,0])   # (year,month,hour,wday) -> [all, fatal, serious]
        for r in rdr:
            try:
                y=int(r[fn['UJAHR']]); mo=int(r[fn['UMONAT']])
                h=int(r[fn['USTUNDE']]); wd=int(r[fn['UWOCHENTAG']])
                kat=int(r[fn['UKATEGORIE']])
            except Exception:
                continue
            a=agg[(y,mo,h,wd)]
            a[0]+=1
            if kat==1: a[1]+=1
            elif kat==2: a[2]+=1
            n+=1
        print("  rows:", n, "cells:", len(agg))
        for (y,mo,h,wd),v in agg.items():
            rows_out.append([y,mo,h,wd,v[0],v[1],v[2]])
    except Exception as ex:
        print("  failed:", ex)

if not rows_out:
    print("FATAL: nothing collected"); sys.exit(1)

rows_out.sort()
with open('de_hourly.csv','w',newline='') as f:
    w=csv.writer(f)
    w.writerow(['year','month','hour','weekday','crashes','fatal','serious'])
    w.writerows(rows_out)
print("de_hourly.csv written:", len(rows_out), "cells")
tot=sum(r[4] for r in rows_out)
print("total crashes:", tot)
