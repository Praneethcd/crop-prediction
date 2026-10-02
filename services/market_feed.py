"""Data.gov.in AGMARKNET current quotes + provenance-preserving daily cache."""
import json
import os
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from services.crop_engine import number, today_local

RESOURCE_ID='9ef84268-d588-465a-a308-a864a43d0070'


class FeedUnavailable(RuntimeError):pass


def canonical(value):return str(value or '').strip().casefold()


def fetch_quotes(lot):
    key=os.getenv('AGMARKNET_API_KEY','')
    if not key:raise FeedUnavailable('Set AGMARKNET_API_KEY in .env to enable live mandi prices')
    params={'api-key':key,'format':'json','limit':500,'offset':0,
            'filters[commodity]':lot['commodity'],'filters[market]':lot['market'],
            'filters[variety]':lot['variety'],'filters[grade]':lot['grade']}
    if lot['state']:params['filters[state]']=lot['state']
    if lot['district']:params['filters[district]']=lot['district']
    records=[]
    # Bounded pagination; fail rather than silently accepting a partial response.
    for page in range(10):
        params['offset']=page*500
        req=Request('https://api.data.gov.in/resource/'+RESOURCE_ID+'?'+urlencode(params),headers={'User-Agent':'AgriPredict/1.0'})
        try:
            with urlopen(req,timeout=20) as response:
                data=json.loads(response.read(4*1024*1024))
        except (URLError,HTTPError,TimeoutError,ValueError):
            # Do not include URL in an error: the query contains the API key.
            raise FeedUnavailable('Government market feed unavailable or API key rejected') from None
        batch=data.get('records')
        if not isinstance(batch,list):raise FeedUnavailable('Market provider returned an invalid response')
        records.extend(batch)
        if len(batch)<500:break
    else:raise FeedUnavailable('Market response exceeds pagination limit; narrow the location')
    matched=[];locations=set()
    for row in records:
        if any(canonical(row.get(k))!=canonical(lot[field]) for k,field in [('commodity','commodity'),('market','market'),('variety','variety'),('grade','grade')]):continue
        if any(lot[field] and canonical(row.get(field))!=canonical(lot[field]) for field in ('state','district')):continue
        try:
            day=datetime.strptime(row['arrival_date'],'%d/%m/%Y').date()
            price=number(row['modal_price'],'provider price',.01)
        except (ValueError,KeyError,TypeError):continue
        if day>today_local():continue
        locations.add((canonical(row.get('state')),canonical(row.get('district'))))
        matched.append({'date':day.isoformat(),'price':price,'source':'AGMARKNET / data.gov.in / '+RESOURCE_ID})
    if len(locations)>1:raise FeedUnavailable('Ambiguous market location; specify state and district')
    if not matched:raise FeedUnavailable('No matching quote; verify official commodity, market, variety, grade and location names')
    grouped={}
    for row in matched:
        if row['date'] in grouped and grouped[row['date']]['price']!=row['price']:
            raise FeedUnavailable('Provider has conflicting daily prices for this selection')
        grouped[row['date']]=row
    return sorted(grouped.values(),key=lambda r:r['date'])


def save_quotes(db,lot_id,rows,source=None):
    for r in rows:
        db.execute('INSERT INTO market_prices(lot_id,price_date,modal_price,source) VALUES (?,?,?,?) ON CONFLICT(lot_id,price_date) DO UPDATE SET modal_price=excluded.modal_price,source=excluded.source,fetched_at=CURRENT_TIMESTAMP',
                   (lot_id,r['date'],r['price'],source or r['source']))


def cached_quotes(db,lot_id):
    return [dict(date=r['price_date'],price=r['modal_price'],source=r['source']) for r in db.execute('SELECT * FROM market_prices WHERE lot_id=? ORDER BY price_date DESC LIMIT 365',(lot_id,))][::-1]


def refresh_quotes(db,lot):
    rows=fetch_quotes(lot);save_quotes(db,lot['id'],rows)
    return cached_quotes(db,lot['id'])
