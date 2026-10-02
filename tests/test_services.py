import json
import unittest
from datetime import date
from unittest.mock import patch
from PIL import Image
from services.market_feed import fetch_quotes,FeedUnavailable
from services.remedies import classify_label,recommendations
from services.vision import load_model,predict


class ProviderTests(unittest.TestCase):
    def test_strict_market_identity_and_pagination(self):
        lot={'crop':'Tomato','commodity':'Tomato','market':'Test','variety':'Local','grade':'FAQ','state':'Tamil Nadu','district':'Test'}
        row={'commodity':'Tomato','market':'Test','variety':'Local','grade':'FAQ','state':'Tamil Nadu','district':'Test','arrival_date':date.today().strftime('%d/%m/%Y'),'modal_price':'5000'}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return json.dumps({'records':[row,{**row,'variety':'Other','modal_price':'9999'}]}).encode()
        with patch.dict('os.environ',{'AGMARKNET_API_KEY':'fixture-key'}),patch('services.market_feed.urlopen',return_value=Response()):
            rows=fetch_quotes(lot)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['price'],5000)

    def test_source_dosage_and_localization(self):
        label=classify_label('Tomato_Late_blight')
        remedy=recommendations(label,'Tamil Nadu','ta')
        self.assertEqual(remedy['chemical'][0]['formulation'],'23% SC')
        self.assertEqual(remedy['chemical'][0]['dose'],200)
        self.assertTrue(remedy['local_match']);self.assertEqual(remedy['language'],'ta')
        self.assertEqual(recommendations(classify_label('Tomato_healthy'))['chemical'],[])
        self.assertEqual(recommendations(classify_label('Tomato__Tomato_mosaic_virus'))['chemical'],[])

    def test_real_trained_artifact_and_quality_rejection(self):
        model,metadata=load_model()
        import torch
        with torch.inference_mode():logits=model(torch.zeros(1,3,224,224))
        self.assertEqual(tuple(logits.shape),(1,15));self.assertEqual(metadata['architecture'],'mobilenet_v3_small')
        with self.assertRaisesRegex(ValueError,'too little detail'):
            predict(Image.new('RGB',(100,100),'green'),'Tomato')
        with self.assertRaisesRegex(ValueError,'supports'):
            predict(Image.new('RGB',(100,100),'green'),'Rice')
