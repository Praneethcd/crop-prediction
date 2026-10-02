import unittest
from datetime import timedelta
from services.crop_engine import today_local
from services.history_import import parse_csv,validate_forecast

class HistoryImportTests(unittest.TestCase):
    def setUp(self):
        self.lot=dict(commodity='Tomato',market='Test',variety='Local',grade='FAQ',state='Tamil Nadu',district='Test')
        self.rows=[(today_local()-timedelta(days=27-i),5000+i*10) for i in range(28)]
    def test_csv_conversion_and_conflicts(self):
        csv='date,price\n'+'\n'.join(f'{d},{p*10}' for d,p in self.rows)
        self.assertEqual(parse_csv(csv.encode(),self.lot,'tonne'),self.rows)
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            parse_csv((csv+f'\n{self.rows[-1][0]},1').encode(),self.lot,'tonne')
    def test_mandi_identity(self):
        csv='Arrival_Date,Modal_Price,Commodity,Market,Variety,Grade,State,District\n'
        csv+='\n'.join(f'{d:%d/%m/%Y},{p},Tomato,Test,Local,FAQ,Tamil Nadu,Test' for d,p in self.rows)
        self.assertEqual(parse_csv(csv.encode(),self.lot),self.rows)
        with self.assertRaises(ValueError):parse_csv(csv.replace('Tomato','Potato').encode(),self.lot)
    def test_holdout_has_no_leakage(self):
        def forecast(training,current,origin,horizon):
            self.assertTrue(all(d<=origin for d,p in training))
            self.assertEqual(len(training),21)
            return [{'date':(origin+timedelta(days=i)).isoformat(),'expected':current} for i in range(1,horizon+1)]
        result=validate_forecast(self.rows,forecast)
        self.assertEqual(result['observations'],7)
        self.assertEqual(result['mae'],40)
        self.assertEqual(result['mae'],result['baseline_mae'])
