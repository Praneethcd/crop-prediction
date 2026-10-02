import io
import json
import secrets
import warnings
from functools import wraps
from pathlib import Path
from datetime import datetime, timezone
from flask import Blueprint, current_app, request, session, jsonify, render_template
from PIL import Image, ImageOps, UnidentifiedImageError
from database import get_db
from services.crop_engine import decide, validate_history, number, today_local
from services.market_feed import refresh_quotes, cached_quotes, save_quotes, FeedUnavailable
from services.monitor import latest_disease, evaluate_lot
from services.remedies import canonical_crop
from services.vision import predict

bp = Blueprint('intelligence', __name__)


def initialize():
    db = get_db()
    db.executescript(Path(__file__).with_name('schema.sql').read_text())
    db.execute('BEGIN IMMEDIATE')
    # Additive migrations for databases created by the first implementation.
    migrations = {
        'crop_lots': [('state', "TEXT NOT NULL DEFAULT ''"), ('district', "TEXT NOT NULL DEFAULT ''"),
                      ('commodity', "TEXT NOT NULL DEFAULT ''"), ('variety', "TEXT NOT NULL DEFAULT 'Other'"), ('language', "TEXT NOT NULL DEFAULT 'en'")],
        'holding_positions': [('source_decision_id', 'INTEGER REFERENCES market_decisions(id)')]
    }
    for table, columns in migrations.items():
        existing = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
        for name, declaration in columns:
            if name not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
    db.execute("UPDATE crop_lots SET commodity=crop WHERE commodity=''")
    db.commit()
    db.close()


def authenticated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify(error='Login required'), 401
        if request.method == 'POST':
            token = session.get('crop_csrf')
            if not token or not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), token):
                return jsonify(error='Invalid CSRF token; reload dashboard'), 403
        try:
            return fn(*args, **kwargs)
        except FeedUnavailable as exc:
            return jsonify(error=str(exc)), 503
        except (RuntimeError, ImportError) as exc:
            current_app.logger.exception('Intelligence service unavailable')
            return jsonify(error='Forecast or image service unavailable. Check dependencies and server logs.'), 503
        except (ValueError, KeyError, TypeError) as exc:
            return jsonify(error=str(exc)), 400
    return wrapped


def owned_lot(db, lot_id):
    row = db.execute('SELECT * FROM crop_lots WHERE id=? AND user_id=?', (lot_id, session['user_id'])).fetchone()
    if not row:
        raise ValueError('Crop lot not found')
    return row


@bp.route('/crop-intelligence')
@authenticated
def dashboard():
    session.setdefault('crop_csrf', secrets.token_hex(32))
    return render_template('crop_intelligence.html', csrf=session['crop_csrf'])


@bp.route('/crop-lots', methods=['GET', 'POST'])
@authenticated
def lots():
    db = get_db()
    try:
        if request.method == 'POST':
            data = request.get_json()
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
            if any(not isinstance(data.get(k),str) for k in ('crop','market','grade')):
                raise ValueError('Crop, market and grade must be text')
            fields = [data[k].strip() for k in ('crop', 'market', 'grade')]
            if any(not s or len(s) > 100 for s in fields):
                raise ValueError('Provide crop, market and grade (up to 100 characters each)')
            commodity=data.get('commodity') or fields[0]
            if not isinstance(commodity,str) or not 1<=len(commodity.strip())<=100:
                raise ValueError('Official commodity name must be text up to 100 characters')
            fields[0] = canonical_crop(fields[0])
            extra = [data.get(k, '') for k in ('state', 'district')]
            variety = data.get('variety', 'Other')
            language = data.get('language', 'en')
            if any(not isinstance(v, str) or len(v)>100 for v in [*extra,variety]) or not variety.strip():
                raise ValueError('State, district and variety must be text up to 100 characters')
            if language not in ('en','hi','ta'):
                raise ValueError('language must be en, hi or ta')
            cursor = db.execute('INSERT INTO crop_lots(user_id,crop,market,grade,state,district,variety,language,commodity) VALUES (?,?,?,?,?,?,?,?,?)',
                                (session['user_id'], *fields, *[v.strip() for v in extra], variety.strip(), language,commodity.strip()))
            db.commit()
            return jsonify(id=cursor.lastrowid), 201
        return jsonify(lots=[dict(r) for r in db.execute('SELECT * FROM crop_lots WHERE user_id=?', (session['user_id'],))])
    finally:
        db.close()


@bp.route('/predict-disease', methods=['POST'])
@authenticated
def disease():
    db = get_db()
    path = None
    try:
        lot = owned_lot(db, request.form.get('lot_id'))
        upload = request.files.get('image')
        if not upload:
            raise ValueError('image is required')
        raw = upload.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError('Image must be at most 5 MB')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                source = Image.open(io.BytesIO(raw))
                if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 16000000:
                    raise ValueError('Use a JPEG, PNG or WebP image below 16 megapixels')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValueError('Invalid or oversized image')
        try:
            result = predict(image, lot['crop'], lot['state'], lot['language'])
        except (RuntimeError, ImportError):
            current_app.logger.exception('Image model unavailable')
            return jsonify(error='Trained image model unavailable; configure artifacts before inference.'), 503
        # Shelf-life evidence is separate from leaf classification and explicitly supplied for this lot.
        compromised = result.get('storage_risk_inferred', False) or request.form.get('storage_compromised') == 'true'
        root = Path(current_app.instance_path) / 'crop_uploads'
        root.mkdir(parents=True, exist_ok=True)
        path = root / (secrets.token_hex(16) + '.jpg')
        image.save(path, 'JPEG')
        cur = db.execute('INSERT INTO disease_assessments(lot_id,image_path,label,confidence,severity,storage_compromised,model_version,result_json) VALUES (?,?,?,?,?,?,?,?)',
                         (lot['id'], str(path), result['label'], result['confidence'], result['severity'], int(compromised), result['model_version'], json.dumps(result)))
        db.commit()
        evaluate_lot(db, lot)
        db.commit()
        return jsonify(id=cur.lastrowid, storage_compromised=compromised, **result), 201
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        db.close()


@bp.route('/market-decision', methods=['POST'])
@authenticated
def market():
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    db = get_db()
    try:
        lot = owned_lot(db, data.get('lot_id'))
        disease = latest_disease(db, lot['id'])
        position = db.execute('SELECT * FROM holding_positions WHERE lot_id=? AND remaining_quintals>0', (lot['id'],)).fetchone()
        if data.get('price_source') == 'live':
            quotes = refresh_quotes(db, lot)
            if not quotes:
                raise ValueError('No market price available')
            data['current_price'] = quotes[-1]['price']
            data['quote_date'] = quotes[-1]['date']
            if (today_local()-datetime.fromisoformat(quotes[-1]['date']).date()).days>3:
                raise ValueError('Latest government quote is stale')
            data['history'] = [{'date':q['date'],'price':q['price']} for q in quotes]
        elif data.get('price_source') == 'cache':
            quotes = cached_quotes(db, lot['id'])
            if not quotes or (today_local()-datetime.fromisoformat(quotes[-1]['date']).date()).days>3:
                raise ValueError('No fresh cached price; sync or enter a verified current quote')
            data['current_price']=quotes[-1]['price']
            data['quote_date']=quotes[-1]['date']
            data['history']=[{'date':q['date'],'price':q['price']} for q in quotes]
        elif data.get('price_source', 'manual') != 'manual':
            raise ValueError('price_source must be live, cache or manual')
        if position and abs(number(data.get('volume_quintals'),'volume_quintals',.001)-position['remaining_quintals'])>1e-6:
            raise ValueError('Volume must equal saved remaining stock')
        result = decide(data, disease, position)
        result['price_source']=data.get('price_source','manual')
        result['quote_date']=data.get('quote_date',today_local().isoformat())
        if data.get('price_source','manual') == 'manual':
            save_quotes(db,lot['id'],[{'date':today_local().isoformat(),'price':number(data['current_price'],'current_price',.01)}],'farmer-entered current quote')
        cur = db.execute('INSERT INTO market_decisions(lot_id,disease_id,input_json,result_json) VALUES (?,?,?,?)',
                         (lot['id'], disease['id'] if disease else None, json.dumps(data), json.dumps(result)))
        if result['urgent']:
            db.execute('INSERT INTO crop_alerts(lot_id,decision_id,message) VALUES (?,?,?)', (lot['id'], cur.lastrowid, result['reason']))
        evaluate_lot(db, lot, position)
        db.commit()
        return jsonify(id=cur.lastrowid, lot_id=lot['id'], **result)
    finally:
        db.close()


@bp.route('/holding-positions', methods=['POST'])
@authenticated
def confirm_holding():
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT d.* FROM market_decisions d JOIN crop_lots l ON l.id=d.lot_id WHERE d.id=? AND l.user_id=?', (data.get('decision_id'), session['user_id'])).fetchone()
        if not row:
            raise ValueError('Decision not found')
        latest = db.execute('SELECT MAX(id) FROM market_decisions WHERE lot_id=?', (row['lot_id'],)).fetchone()[0]
        if latest != row['id']:
            raise ValueError('Confirm the latest decision only')
        result = json.loads(row['result_json'])
        disease=latest_disease(db,row['lot_id'])
        if result['hold_quintals']>0 and disease and disease['severity']=='severe' and disease['confidence']>=.9:
            raise ValueError('A newer severe assessment prevents holding. Calculate a new decision.')
        if (datetime.now(timezone.utc)-datetime.fromisoformat(row['created_at']).replace(tzinfo=timezone.utc)).total_seconds()>3600:
            raise ValueError('Decision is over one hour old; calculate again before confirming')
        db.execute('INSERT INTO holding_positions(lot_id,reference_price,stop_loss_price,remaining_quintals,source_decision_id) VALUES (?,?,?,?,?) ON CONFLICT(lot_id) DO UPDATE SET remaining_quintals=excluded.remaining_quintals,source_decision_id=excluded.source_decision_id,updated_at=CURRENT_TIMESTAMP',
                   (row['lot_id'], result['reference_price'], result['stop_loss_price'], result['hold_quintals'],row['id']))
        db.commit()
        return jsonify(remaining_quintals=result['hold_quintals'])
    finally:
        db.close()


@bp.route('/market-prices', methods=['GET','POST'])
@authenticated
def prices():
    data=request.get_json() if request.method=='POST' else request.args
    if not data:raise ValueError('lot_id is required')
    db=get_db()
    try:
        lot=owned_lot(db,data.get('lot_id'))
        rows=refresh_quotes(db,lot) if request.method=='POST' else cached_quotes(db,lot['id'])
        db.commit()
        return jsonify(prices=rows,source='AGMARKNET cache',
                       current_price=rows[-1]['price'] if rows else None,
                       needs_history=len(rows)<14)
    finally:db.close()


@bp.route('/market-history', methods=['POST'])
@authenticated
def import_history():
    data=request.get_json()
    if not isinstance(data,dict):raise ValueError('JSON object required')
    dated=validate_history(data.get('history'))
    db=get_db()
    try:
        lot=owned_lot(db,data.get('lot_id'))
        save_quotes(db,lot['id'],[{'date':d.isoformat(),'price':p} for d,p in dated],'farmer-imported history')
        db.commit()
        return jsonify(imported=len(dated))
    finally:db.close()


@bp.route('/crop-lots/<int:lot_id>/history')
@authenticated
def lot_history(lot_id):
    db=get_db()
    try:
        owned_lot(db,lot_id)
        position=db.execute('SELECT * FROM holding_positions WHERE lot_id=?',(lot_id,)).fetchone()
        assessments=[dict(r) for r in db.execute('SELECT id,label,confidence,severity,storage_compromised,result_json,created_at FROM disease_assessments WHERE lot_id=? ORDER BY id DESC LIMIT 10',(lot_id,))]
        decisions=[dict(r) for r in db.execute('SELECT id,result_json,created_at FROM market_decisions WHERE lot_id=? ORDER BY id DESC LIMIT 10',(lot_id,))]
        for r in assessments+decisions:r['result']=json.loads(r.pop('result_json'))
        return jsonify(position=dict(position) if position else None,assessments=assessments,decisions=decisions)
    finally:db.close()


@bp.route('/crop-alerts')
@authenticated
def alerts():
    db=get_db()
    try:
        rows=db.execute('SELECT a.*,l.crop,l.market FROM alert_events a JOIN crop_lots l ON l.id=a.lot_id WHERE l.user_id=? AND a.acknowledged_at IS NULL ORDER BY a.id DESC LIMIT 50',(session['user_id'],)).fetchall()
        return jsonify(alerts=[dict(r) for r in rows])
    finally:db.close()


@bp.route('/crop-alerts/<int:alert_id>/acknowledge', methods=['POST'])
@authenticated
def acknowledge(alert_id):
    db=get_db()
    try:
        cur=db.execute('UPDATE alert_events SET acknowledged_at=CURRENT_TIMESTAMP WHERE id=? AND lot_id IN (SELECT id FROM crop_lots WHERE user_id=?)',(alert_id,session['user_id']))
        if not cur.rowcount:raise ValueError('Alert not found')
        db.commit();return jsonify(acknowledged=True)
    finally:db.close()


@bp.route('/intelligence-status')
@authenticated
def status():
    from services.vision import load_model
    try:
        _,metadata=load_model();vision={'ready':True,'model':metadata['version'],'crops':sorted({r['crop'] for r in metadata['classes']})}
    except (ImportError,RuntimeError):vision={'ready':False,'error':'Install dependencies and run scripts/setup_vision.py'}
    import importlib.util
    db=get_db()
    try:
        monitor=db.execute('SELECT * FROM monitor_runs WHERE id=1').fetchone()
        return jsonify(vision=vision,prophet_ready=importlib.util.find_spec('prophet') is not None,
                       live_feed_configured=bool(__import__('os').getenv('AGMARKNET_API_KEY')),
                       monitor=dict(monitor) if monitor else {'status':'not_started'})
    finally:db.close()
