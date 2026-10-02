import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from PIL import Image
import database
from services.crop_engine import decide
from services.routes import bp, initialize


def payload():
    return {'lot_id':1,'current_price':5000,'volume_quintals':10,'cash_required':20000,
            'history':[{'date':(date.today()-timedelta(days=29-i)).isoformat(),'price':4000+i*40} for i in range(30)]}


class EngineTests(unittest.TestCase):
    def test_cash_constraint(self):
        result=decide(payload())
        self.assertGreaterEqual(result['sell_pct'],40)
        self.assertGreaterEqual(result['cash_raised'],20000)
        self.assertEqual(result['hold_pct']+result['sell_pct'],100)

    def test_override(self):
        d={'severity':'severe','confidence':.95,'storage_compromised':1}
        self.assertEqual(decide(payload(),d)['sell_pct'],100)
        d['storage_compromised']=0
        self.assertTrue(decide(payload(),d)['urgent'])
        d.update(storage_compromised=1,confidence=.89)
        self.assertFalse(decide(payload(),d)['urgent'])

    def test_stop_loss(self):
        result=decide(payload(),position={'reference_price':6000,'stop_loss_price':5400})
        self.assertTrue(result['urgent'])
        self.assertEqual(result['sell_pct'],100)

    def test_invalid_history(self):
        p=payload();p['history'][0]['date']=p['history'][1]['date']
        with self.assertRaises(ValueError):decide(p)
        p=payload();p['current_price']=float('nan')
        with self.assertRaises(ValueError):decide(p)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=database.DATABASE
        database.DATABASE=str(Path(self.tmp.name)/'test.db');database.init_db();initialize()
        self.app=Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1]/'templates'));self.app.secret_key='test';self.app.instance_path=self.tmp.name
        for endpoint in ('manifest','index','crop_recommendation','yield_prediction','disease_prediction','fertilizer_recommendation','weather_prediction','farmer_connect','about','dashboard','admin_dashboard','logout','login','register'):
            self.app.add_url_rule('/test/'+endpoint,endpoint,lambda: '')
        self.app.register_blueprint(bp);self.client=self.app.test_client()
        with self.client.session_transaction() as s:s['user_id']=1;s['crop_csrf']='token'
        self.headers={'X-CSRF-Token':'token'}
        self.client.post('/crop-lots',json={'crop':'Tomato','market':'Test','grade':'A'},headers=self.headers)

    def tearDown(self):
        database.DATABASE=self.old;self.tmp.cleanup()

    def test_auth_and_csrf(self):
        self.assertEqual(self.client.post('/market-decision',json=payload()).status_code,403)
        other=self.app.test_client();self.assertEqual(other.get('/crop-lots').status_code,401)

    def test_ownership(self):
        with self.client.session_transaction() as s:s['user_id']=999
        self.assertEqual(self.client.post('/market-decision',json=payload(),headers=self.headers).status_code,400)

    def test_persisted_override(self):
        db=database.get_db();db.execute("INSERT INTO disease_assessments(lot_id,image_path,label,confidence,severity,storage_compromised,model_version,result_json) VALUES (1,'private.jpg','Late blight',.95,'severe',1,'v1','{}')");db.commit();db.close()
        r=self.client.post('/market-decision',json=payload(),headers=self.headers)
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['sell_pct'],100)
        db=database.get_db();self.assertEqual(db.execute('SELECT COUNT(*) FROM crop_alerts').fetchone()[0],1);db.close()

    def test_upload_and_unavailable(self):
        r=self.client.post('/predict-disease',data={'lot_id':'1','image':(io.BytesIO(b'bad'),'leaf.jpg')},headers=self.headers)
        self.assertEqual(r.status_code,400)
        image=io.BytesIO();Image.new('RGB',(30,30),'green').save(image,'PNG');image.seek(0)
        with patch('services.routes.predict',side_effect=RuntimeError('not configured')):
            r=self.client.post('/predict-disease',data={'lot_id':'1','image':(image,'leaf.png')},headers=self.headers)
        self.assertEqual(r.status_code,503)

    def test_holding_reference_persists(self):
        with patch('services.crop_engine.forecast_prices',return_value=[{'date':(date.today()+timedelta(days=7)).isoformat(),'expected':5500,'low':5000,'high':6000}]):
            r=self.client.post('/market-decision',json=payload(),headers=self.headers)
        saved=self.client.post('/holding-positions',json={'decision_id':r.json['id']},headers=self.headers)
        p=payload();p['volume_quintals']=saved.json['remaining_quintals'];p['current_price']=4400
        r=self.client.post('/market-decision',json=p,headers=self.headers)
        self.assertEqual(r.json['sell_pct'],100);self.assertEqual(r.json['stop_loss_price'],4500)

    def test_dashboard(self):
        self.assertEqual(self.client.get('/crop-intelligence').status_code,200)


if __name__=='__main__':unittest.main()


class IntegrationTests(ApiTests):
    def test_severe_override_without_forecast(self):
        p=payload();p.pop('history')
        d={'severity':'severe','confidence':.99,'storage_compromised':0}
        with patch('services.crop_engine.forecast_prices',side_effect=AssertionError('must bypass forecast')):
            result=decide(p,d)
        self.assertTrue(result['disease_override']);self.assertEqual(result['forecast'],[])

    def test_cache_import_and_decision(self):
        p=payload()
        response=self.client.post('/market-history',json={'lot_id':1,'history':p['history']},headers=self.headers)
        self.assertEqual(response.status_code,200)
        quotes=self.client.get('/market-prices?lot_id=1').json['prices']
        self.assertEqual(len(quotes),30)
        p.pop('history');p.pop('current_price');p['price_source']='cache'
        r=self.client.post('/market-decision',json=p,headers=self.headers)
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json['forecast']),7)
        self.assertIn('Prophet',r.json['model'])

    def test_background_stop_loss_deduplicated_and_owned(self):
        from services.monitor import run_once
        db=database.get_db()
        db.execute('INSERT INTO holding_positions(lot_id,reference_price,stop_loss_price,remaining_quintals) VALUES (1,5000,4500,6)')
        db.execute("INSERT INTO market_prices(lot_id,price_date,modal_price,source) VALUES (?,?,4400,'fixture')",(1,date.today().isoformat()))
        db.commit();db.close()
        with patch.dict('os.environ',{'AGMARKNET_API_KEY':''}):
            result=run_once();self.assertEqual(result['new_alerts'],1)
            result=run_once();self.assertEqual(result['new_alerts'],0)
        alerts=self.client.get('/crop-alerts').json['alerts'];self.assertEqual(len(alerts),1)
        id=alerts[0]['id'];self.assertEqual(alerts[0]['kind'],'stop_loss')
        with self.client.session_transaction() as s:s['user_id']=999
        self.assertEqual(self.client.post(f'/crop-alerts/{id}/acknowledge',json={},headers=self.headers).status_code,400)
        with self.client.session_transaction() as s:s['user_id']=1
        self.assertEqual(self.client.post(f'/crop-alerts/{id}/acknowledge',json={},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/crop-alerts').json['alerts'],[])

    def test_missing_live_key(self):
        with patch.dict('os.environ',{'AGMARKNET_API_KEY':''}):
            r=self.client.post('/market-prices',json={'lot_id':1},headers=self.headers)
        self.assertEqual(r.status_code,503)

    def test_disease_upload_triggers_holding_alert(self):
        db=database.get_db();db.execute('INSERT INTO holding_positions(lot_id,reference_price,stop_loss_price,remaining_quintals) VALUES (1,5000,4500,6)');db.commit();db.close()
        image=io.BytesIO();Image.new('RGB',(100,100),'green').save(image,'PNG');image.seek(0)
        result={'label':'Tomato Late blight','crop':'Tomato','disease':'Late blight','severity':'severe',
                'confidence':.99,'storage_risk_inferred':True,'model_version':'test','remedies':{}}
        with patch('services.routes.predict',return_value=result):
            r=self.client.post('/predict-disease',data={'lot_id':'1','image':(image,'leaf.png')},headers=self.headers)
        self.assertEqual(r.status_code,201)
        self.assertEqual(self.client.get('/crop-alerts').json['alerts'][0]['kind'],'disease')
        p=payload();p['volume_quintals']=6;p.pop('history')
        r=self.client.post('/market-decision',json=p,headers=self.headers)
        self.assertEqual(r.json['sell_pct'],100);self.assertTrue(r.json['disease_override'])

    def test_stale_assessment_not_used(self):
        db=database.get_db()
        db.execute("INSERT INTO disease_assessments(lot_id,image_path,label,confidence,severity,storage_compromised,model_version,result_json,created_at) VALUES (1,'private.jpg','Late blight',.99,'severe',1,'v1','{}','2000-01-01 00:00:00')");db.commit();db.close()
        r=self.client.post('/market-decision',json=payload(),headers=self.headers)
        self.assertEqual(r.status_code,200);self.assertFalse(r.json['disease_override'])

    def test_invalid_json(self):
        for endpoint in ('/crop-lots','/market-decision','/holding-positions','/market-history'):
            self.assertEqual(self.client.post(endpoint,json=[],headers=self.headers).status_code,400)
