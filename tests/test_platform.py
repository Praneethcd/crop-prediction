"""Smoke-test the complete existing platform alongside the new features."""
import importlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.environment=patch.dict('os.environ',{'AGRIPREDICT_DATABASE':str(Path(cls.tmp.name)/'platform.db'),'APP_ENV':'test'})
        cls.environment.start()
        cls.app=importlib.import_module('app').app

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop();cls.tmp.cleanup()

    def setUp(self):self.client=self.app.test_client()

    def test_health_and_public_pages(self):
        for path in ('/','/about','/login','/register','/crop-recommendation','/yield-prediction','/disease-prediction','/fertilizer-recommendation','/weather-prediction','/farmer-connect'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.get('/healthz').json['status'],'ok')

    def test_existing_prediction_apis(self):
        examples={
            '/api/predict-yield':{'rainfall':700,'pesticide':100,'temperature':28,'crop':'Maize'},
            '/api/predict-disease':{'rainfall':700,'temperature':28,'humidity':70},
            '/api/predict-weather':{'year':2026},
            '/api/recommend-fertilizer':{'crop':'Maize','rainfall':700}
        }
        for path,data in examples.items():
            with self.subTest(path=path):
                response=self.client.post(path,json=data)
                self.assertEqual(response.status_code,200);self.assertTrue(response.json['success'],response.json)

    def test_login_and_intelligence_status(self):
        response=self.client.post('/login',data={'email':'admin@agripredict.com','password':'admin123'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get('/crop-intelligence').status_code,200)
        status=self.client.get('/intelligence-status').json
        self.assertTrue(status['vision']['ready']);self.assertTrue(status['prophet_ready'])

    def test_pwa_and_private_cache_policy(self):
        manifest=self.client.get('/manifest.webmanifest')
        self.assertEqual(manifest.status_code,200);self.assertEqual(manifest.json['display'],'standalone')
        worker=self.client.get('/service-worker.js')
        self.assertEqual(worker.status_code,200)
        self.assertNotIn('/crop-intelligence',worker.text)
        offline=self.client.get('/static/offline.html')
        self.assertEqual(offline.status_code,200)
        offline.close();manifest.close();worker.close()
