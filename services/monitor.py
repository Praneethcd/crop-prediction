"""Persistent, deduplicated in-app alerts and a standalone market-monitor worker."""
import argparse
import json
import logging
import os
import threading
import time
from datetime import datetime,timezone,date
from database import get_db
from services.crop_engine import today_local
from services.market_feed import refresh_quotes,cached_quotes,FeedUnavailable

log=logging.getLogger(__name__)


def latest_disease(db,lot_id):
    row=db.execute('SELECT * FROM disease_assessments WHERE lot_id=? ORDER BY id DESC LIMIT 1',(lot_id,)).fetchone()
    if row:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['created_at']).replace(tzinfo=timezone.utc)).total_seconds()
        if not 0<=age<=86400:return None
    return row


def evaluate_lot(db,lot,position=None):
    position=position or db.execute('SELECT * FROM holding_positions WHERE lot_id=? AND remaining_quintals>0',(lot['id'],)).fetchone()
    if not position:return 0
    disease=latest_disease(db,lot['id'])
    quotes=cached_quotes(db,lot['id'])
    fresh=quotes and 0<=(today_local()-date.fromisoformat(quotes[-1]['date'])).days<=3
    price=quotes[-1]['price'] if fresh else None
    generation=position['source_decision_id'] or position['updated_at']
    kind=message=event=None
    if disease and disease['severity']=='severe' and disease['confidence']>=.9:
        kind='disease';event=f"disease:{lot['id']}:{disease['id']}:{generation}"
        message='SELL 100% IMMEDIATELY of remaining marketable stock: severe high-confidence disease. Storage risk is inferred; segregate spoiled produce.'
    elif price is not None and price<=position['stop_loss_price']:
        kind='stop_loss';event=f"stop_loss:{lot['id']}:{generation}"
        message=f"STOP LOSS: ₹{price:g}/quintal is at or below ₹{position['stop_loss_price']:g}. Sell remaining {position['remaining_quintals']:g} quintals of marketable stock."
    if not event:return 0
    cur=db.execute('INSERT OR IGNORE INTO alert_events(lot_id,kind,event_key,message,price) VALUES (?,?,?,?,?)',(lot['id'],kind,event,message,price))
    return cur.rowcount


def run_once():
    db=get_db();started=time.time()
    try:
        db.execute('INSERT OR IGNORE INTO monitor_leases(id,expires_at) VALUES (1,0)')
        cur=db.execute('UPDATE monitor_leases SET expires_at=? WHERE id=1 AND expires_at<?',(started+1800,started))
        db.commit()
        if not cur.rowcount:return {'status':'already_running'}
        lots=db.execute('SELECT l.* FROM crop_lots l JOIN holding_positions h ON h.lot_id=l.id WHERE h.remaining_quintals>0').fetchall()
        errors=[];alerts=0
        for lot in lots:
            try:
                if os.getenv('AGMARKNET_API_KEY'):
                    refresh_quotes(db,lot);db.commit()
            except FeedUnavailable as exc:
                errors.append({'lot_id':lot['id'],'error':str(exc)})
            try:
                quotes=cached_quotes(db,lot['id'])
                if not quotes or (today_local()-date.fromisoformat(quotes[-1]['date'])).days>3:
                    errors.append({'lot_id':lot['id'],'error':'No fresh quote; price stop-loss check skipped'})
                alerts+=evaluate_lot(db,lot);db.commit()
            except Exception:
                db.rollback();errors.append({'lot_id':lot['id'],'error':'Monitor check failed; see server log'})
                log.exception('Monitor lot %s failed',lot['id'])
        details={'checked_lots':len(lots),'new_alerts':alerts,'errors':errors,'duration_seconds':round(time.time()-started,2)}
        status='degraded' if errors else 'ok'
        db.execute('INSERT INTO monitor_runs(id,last_run,status,details_json) VALUES (1,CURRENT_TIMESTAMP,?,?) ON CONFLICT(id) DO UPDATE SET last_run=CURRENT_TIMESTAMP,status=excluded.status,details_json=excluded.details_json',(status,json.dumps(details)))
        db.commit()
        return {'status':status,**details}
    finally:
        # Only release a lease acquired by this process.
        db.execute('UPDATE monitor_leases SET expires_at=0 WHERE id=1 AND expires_at=?',(started+1800,))
        db.commit();db.close()


def start_monitor(interval=900):
    stop=threading.Event()
    def loop():
        while not stop.is_set():
            try:run_once()
            except Exception:log.exception('Market monitor failed')
            stop.wait(interval)
    threading.Thread(target=loop,name='crop-price-monitor',daemon=True).start()
    return stop


def main():
    from dotenv import load_dotenv
    load_dotenv()
    from services.routes import initialize
    from database import init_db
    init_db();initialize()
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--interval',type=int,default=900)
    args=parser.parse_args()
    if args.once:print(json.dumps(run_once()));return
    if args.interval<30:parser.error('interval must be at least 30 seconds')
    logging.basicConfig(level=logging.INFO)
    while True:
        log.info('Monitor result: %s',run_once());time.sleep(args.interval)


if __name__=='__main__':main()
