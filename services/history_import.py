"""Import real observations and measure a chronological forecast holdout."""
import csv
import io
import re
from datetime import datetime
from services.crop_engine import validate_history, number
from services.forecasting import forecast_prices


def parse_csv(raw, lot, unit='quintal'):
    factors={'quintal':1,'tonne':.1,'kg':100}
    if unit not in factors:raise ValueError('Choose quintal, tonne or kg price units')
    if len(raw)>1024*1024:raise ValueError('CSV exceeds 1 MB')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:raise ValueError('CSV must use UTF-8 encoding') from None
    reader=csv.DictReader(io.StringIO(text))
    norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
    headers={norm(h):h for h in (reader.fieldnames or [])}
    date_key=headers.get('date') or headers.get('arrivaldate')
    price_key=headers.get('price') or headers.get('modalprice')
    if not date_key or not price_key:raise ValueError('CSV needs date,price or Arrival_Date,Modal_Price columns')
    result={};locations=set()
    for index,row in enumerate(reader):
        if index>=10000:raise ValueError('CSV exceeds 10,000 rows')
        if None in row:raise ValueError('Malformed CSV row')
        mismatch=False
        for field in ('commodity','market','variety','grade','state','district'):
            key=headers.get(field)
            if key and lot[field] and str(row.get(key,'')).strip().casefold()!=str(lot[field]).strip().casefold():mismatch=True
        if mismatch:continue
        locations.add(tuple(str(row.get(headers.get(k), '')).strip().casefold() for k in ('state','district')))
        value=str(row.get(date_key,'')).strip();day=None
        for fmt in ('%Y-%m-%d','%d/%m/%Y'):
            try:day=datetime.strptime(value,fmt).date();break
            except ValueError:pass
        if day is None:raise ValueError('Dates must use YYYY-MM-DD or DD/MM/YYYY')
        price=number(row.get(price_key),'CSV price',.01)*factors[unit]
        if day in result and result[day]!=price:raise ValueError('Conflicting prices for the same date')
        result[day]=price
    if len(locations)>1:raise ValueError('Ambiguous location; specify state and district for the lot')
    return validate_history([{'date':d.isoformat(),'price':p} for d,p in sorted(result.items())])


def validate_forecast(rows, forecaster=forecast_prices):
    if len(rows)<28:raise ValueError('At least 28 observations required for forecast validation')
    # Hold out the last calendar week. No held-out prices enter model fitting.
    end=rows[-1][0]
    training=[r for r in rows if (end-r[0]).days>=7]
    if len(training)<14:raise ValueError('Insufficient training observations')
    origin=training[-1][0]
    held=[r for r in rows if 0<(r[0]-origin).days<=15]
    if not held:raise ValueError('No observations within the validation horizon')
    horizon=max(7,max((d-origin).days for d,p in held))
    predictions={r['date']:r['expected'] for r in forecaster(training,training[-1][1],origin,horizon)}
    errors=[predictions[d.isoformat()]-p for d,p in held]
    baseline=[training[-1][1]-p for d,p in held]
    return {'observations':len(held),'training_observations':len(training),
            'from_date':held[0][0].isoformat(),'to_date':held[-1][0].isoformat(),
            'mae':round(sum(abs(e) for e in errors)/len(errors),2),
            'rmse':round((sum(e*e for e in errors)/len(errors))**.5,2),
            'mape_pct':round(100*sum(abs(e)/p for e,(_,p) in zip(errors,held))/len(errors),2),
            'baseline_mae':round(sum(abs(e) for e in baseline)/len(baseline),2),
            'notice':'Single chronological holdout on supplied prices; future accuracy is not guaranteed.'}
