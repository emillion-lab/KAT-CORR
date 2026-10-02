#!/usr/bin/env python3
"""Локален тест на налягането (хипотеза на Емил, 02.10.2026):
рязък спад на налягането работи локално, но се размазва при голяма територия,
защото фронтът минава през различни места в различни дни.

Данни: STATS19 (всяка катастрофа с дата и полицейски район), 2021–2025.
Всеки от TOP-те района получава метео от СОБСТВЕНИЯ си център (Open-Meteo archive).
Контрола: същите райони с ЕДНА обща точка за цялата страна.
Откриване 2021–2023, проверка 2024–2025 (невидени години).
Изход: results/uk_local_pressure.md
"""
import csv, io, json, math, os, sys, time, statistics as st
import urllib.request, datetime as D, collections
import numpy as np

URL = 'https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-last-5-years.csv'
TOP = 10
DISC = lambda d: d.year <= 2023
VAL  = lambda d: d.year >= 2024
# Британският локдаун (01–06.2021) сваля катастрофите с ~28% точно в бурния сезон,
# а годишната фиктивна го размазва — изключва се изцяло.
SKIP = lambda d: D.date(2021, 1, 1) <= d <= D.date(2021, 6, 30)
OUT  = 'results/uk_local_pressure_nolockdown.md'
DAILY = ('surface_pressure_mean,precipitation_sum,snowfall_sum,temperature_2m_min,'
         'temperature_2m_max,wind_speed_10m_max,sunshine_duration,daylight_duration')
NAMES = {'1':'Лондон (Met)','4':'Ланкашър','5':'Мърсисайд','6':'Голям Манчестър',
         '13':'Западен Йоркшър','14':'Южен Йоркшър','20':'Уест Мидландс',
         '43':'Темза Вали','44':'Хампшър','46':'Кент','47':'Съсекс',
         '50':'Девън и Корнуол','52':'Ейвън и Съмърсет'}

def fetch(url, tries=3):
    # User-Agent като браузър: DfT държи висящи заявки с непознат UA
    # (fetch_uk.py със същия файл минава с 'Mozilla/5.0').
    for i in range(tries):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=180) as r:
                b = r.read()
            print(f'  {len(b)//1024} KB за {time.time()-t0:.0f}s ← {url[:80]}', flush=True)
            return b
        except Exception as e:
            print(f'  опит {i+1} ({time.time()-t0:.0f}s): {e}', flush=True); time.sleep(10 * (i + 1))
    raise SystemExit('свалянето пропадна: ' + url)

def pdate(s):
    s = (s or '').strip()
    for f in ('%d/%m/%Y', '%Y-%m-%d'):
        try: return D.datetime.strptime(s, f).date()
        except ValueError: pass
    return None

# ---------- катастрофи по район и ден ----------
print('STATS19…', flush=True)
raw = fetch(URL).decode('utf-8-sig', errors='replace')
cnt = collections.defaultdict(collections.Counter)
cas = collections.defaultdict(collections.Counter)
pts = collections.defaultdict(list)
dmin, dmax = None, None
for r in csv.DictReader(io.StringIO(raw)):
    d = pdate(r.get('date')); pf = (r.get('police_force') or '').strip()
    if not d or not pf: continue
    dmin = d if dmin is None or d < dmin else dmin
    dmax = d if dmax is None or d > dmax else dmax
    cnt[pf][d] += 1
    try: cas[pf][d] += int(r.get('number_of_casualties') or 0)
    except ValueError: pass
    if len(pts[pf]) < 30000:
        try: pts[pf].append((float(r['latitude']), float(r['longitude'])))
        except (ValueError, KeyError, TypeError): pass
del raw
forces = sorted(cnt, key=lambda k: -sum(cnt[k].values()))[:TOP]
centre = {pf: (st.median(p[0] for p in pts[pf]), st.median(p[1] for p in pts[pf])) for pf in forces}
allp = [p for pf in forces for p in pts[pf]]
national = (st.median(p[0] for p in allp), st.median(p[1] for p in allp))
print(f'дни {dmin}..{dmax}; райони: {forces}', flush=True)

# ---------- метео ----------
def weather(lat, lon):
    u = (f'https://archive-api.open-meteo.com/v1/archive?latitude={lat:.3f}&longitude={lon:.3f}'
         f'&start_date={dmin}&end_date={dmax}&daily={DAILY}&timezone=Europe%2FLondon')
    dd = json.loads(fetch(u))['daily']
    return {D.date.fromisoformat(t): {k: dd[k][i] for k in dd if k != 'time'}
            for i, t in enumerate(dd['time'])}
W = {}
for pf in forces:
    W[pf] = weather(*centre[pf]); time.sleep(2)
WN = weather(*national)

# ---------- анализ ----------
def feats(d, w):
    v = [1.0] + [1.0*(d.year == y) for y in range(dmin.year+1, dmax.year+1)]
    v += [1.0*(d.weekday() == k) for k in range(6)] + [1.0*(d.month == k) for k in range(2, 13)]
    rn = w.get('precipitation_sum') or 0
    v += [1.0*(rn >= t) for t in (0.5, 2, 5, 10, 20)]
    v += [1.0*((w.get('snowfall_sum') or 0) >= 0.5)]
    dl = w.get('daylight_duration'); s = (w.get('sunshine_duration') or 0)/dl if dl else 0.5
    v += [s, s*s]
    tmin = w.get('temperature_2m_min'); v += [1.0*(tmin is not None and tmin <= 0)]
    v += [1.0*((w.get('wind_speed_10m_max') or 0) >= 40)]
    return v

def dpbin(x):
    if x is None: return None
    return 'спад >8' if x < -8 else 'спад 5–8' if x < -5 else 'ръст >5' if x > 5 else 'стабилно'

def residuals(pf, Wx, series):
    rows = []
    d = dmin + D.timedelta(days=1)
    while d <= dmax:
        w, w0 = Wx.get(d), Wx.get(d - D.timedelta(days=1))
        if w and w0 and not SKIP(d) and w.get('surface_pressure_mean') is not None and w0.get('surface_pressure_mean') is not None:
            rows.append((d, feats(d, w), math.log(series[pf].get(d, 0) + 0.5),
                         w['surface_pressure_mean'] - w0['surface_pressure_mean']))
        d += D.timedelta(days=1)
    X = np.array([r[1] for r in rows]); y = np.array([r[2] for r in rows])
    m = np.array([DISC(r[0]) for r in rows])
    b = np.linalg.lstsq(X[m], y[m], rcond=None)[0]
    res = y - X @ b
    return [(r[0], e, dpbin(r[3])) for r, e in zip(rows, res)]

def effects(rows, period):
    sub = [r for r in rows if period(r[0]) and r[2]]
    mu = st.mean(r[1] for r in sub); g = collections.defaultdict(list)
    for r in sub: g[r[2]].append(r[1] - mu)
    return {k: (100*(math.exp(st.mean(v))-1), 100*st.stdev(v)/math.sqrt(len(v)), len(v))
            for k, v in g.items() if len(v) >= 8}

BINS = ['спад >8', 'спад 5–8', 'стабилно', 'ръст >5']
def table(rows):
    a, b = effects(rows, DISC), effects(rows, VAL)
    out = ['| Δ налягане (hPa) | 2021–23 | 2024–25 | повтаря ли се |', '|---|---|---|---|']
    for k in BINS:
        if k not in a or k not in b: continue
        ok = a[k][0]*b[k][0] > 0 and abs(a[k][0]) > 2*a[k][1] and abs(b[k][0]) > 2*b[k][1]
        out.append(f'| {k} | {a[k][0]:+.1f}% ±{a[k][1]:.1f} (n={a[k][2]}) | '
                   f'{b[k][0]:+.1f}% ±{b[k][1]:.1f} (n={b[k][2]}) | {"✓" if ok else ""} |')
    return '\n'.join(out)

md = [f'# Налягане — локален тест (STATS19, {dmin}..{dmax})', '',
      f'Генерирано: {D.datetime.utcnow():%Y-%m-%d %H:%M} UTC. Откриване 07.2021–2023 (без локдауна 01–06.2021), проверка 2024–25.',
      'Ефект = отклонение от обичайното след контрол за година, ден, месец, дъжд, сняг, слънце, мраз, вятър.',
      'Ако хипотезата е вярна: ЛОКАЛНО има ефект, ОБЩА ТОЧКА — по-слаб или никакъв.', '']
for label, series in (('катастрофи', cnt), ('пострадали', cas)):
    loc, nat = [], []
    for pf in forces:
        loc += residuals(pf, W[pf], series)
        nat += residuals(pf, WN, series)
    md += [f'## {label} — ЛОКАЛНО (всеки район със своето налягане)', table(loc), '',
           f'## {label} — ОБЩА ТОЧКА ({national[0]:.2f}, {national[1]:.2f}) за всички', table(nat), '']
md += ['## По райони — катастрофи, „спад >5" спрямо стабилно, локално', '',
       '| район | център | 2021–23 | 2024–25 |', '|---|---|---|---|']
for pf in forces:
    r = residuals(pf, W[pf], cnt)
    r = [(d, e, ('спад' if b in ('спад >8', 'спад 5–8') else b)) for d, e, b in r]
    a, b = effects(r, DISC), effects(r, VAL)
    f = lambda e: f'{e["спад"][0]:+.1f}% ±{e["спад"][1]:.1f}' if 'спад' in e else '—'
    md.append(f'| {NAMES.get(pf, pf)} | {centre[pf][0]:.2f}, {centre[pf][1]:.2f} | {f(a)} | {f(b)} |')
os.makedirs('results', exist_ok=True)
open(OUT, 'w').write('\n'.join(md) + '\n')
print('\n'.join(md))
