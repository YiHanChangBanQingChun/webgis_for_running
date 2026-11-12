"""Small deterministic tests; no network and no real database writes."""
import sqlite3
import unittest
from pathlib import Path
import track_training as tracking


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript(tracking.SCHEMA)

    def tearDown(self):
        self.db.close()

    def test_unwrap_double_encoded_tool_text(self):
        self.assertEqual(tracking.unwrap({'content':[{'type':'text','text':'"A\\nB"'}]}),'A\nB')

    def test_official_daily_fields_merge(self):
        tracking.update_daily(self.db,'2026-09-14',{'hrv_ms':96,'hrv_status':'Normal'})
        tracking.update_daily(self.db,'2026-09-14',{'load_ratio':1.21})
        self.assertEqual(self.db.execute('SELECT hrv_ms,load_ratio FROM daily_metrics').fetchone()[:],(96,1.21))

    def test_identifier_is_text_and_week_is_monday(self):
        tracking.put(self.db,'activities',{'activity_id':'480309782006235139','date_cn':'2026-09-13','source':'test','distance_km':15,'duration_s':4915},'activity_id')
        tracking.put(self.db,'activities',{'activity_id':'480309782006235139','date_cn':'2026-09-13','source':'test','distance_km':15,'duration_s':4915},'activity_id')
        self.assertEqual(self.db.execute('SELECT count(*),typeof(activity_id) FROM activities').fetchone()[:],(1,'text'))
        self.assertEqual(self.db.execute('SELECT week_monday FROM weekly_training').fetchone()[0],'2026-09-07')

    def test_hrv_raw_points_not_used(self):
        text='2026-09-14:\n  HRV Avg: 96 ms — Normal\n  Normal Range: 93 - 109 ms\n  Baseline: 101 ms\nSleep HRV Time Series\n2026-09-14:\n  HRV Avg: 999 ms — Normal\n  Normal Range: 1 - 999 ms\n  Baseline: 999 ms'
        tracking.import_hrv(self.db,{'content':[{'type':'text','text':text}]})
        self.assertEqual(self.db.execute('SELECT hrv_ms FROM daily_metrics').fetchone()[0],96)

    def test_failed_tool_not_imported(self):
        with self.assertRaises(ValueError): tracking.unwrap({'isError':True,'content':[]})

    def test_fit_and_coros_are_deduplicated_and_mixed_record_excluded(self):
        tracking.put(self.db,'activities',{'activity_id':'123','date_cn':'2026-10-03','source':'COROS_MCP','distance_km':12,'duration_s':4000},'activity_id')
        for aid,include in [('123',1),('456',1),('789',0)]:
            tracking.put(self.db,'fit_observations',{'activity_id':aid,'date_cn':'2026-10-03','sport':'running',
                'source':'LOCAL_FIT','distance_km':5,'duration_s':1800,'include_formal':include,'raw_json':'{}'},'activity_id')
        row=self.db.execute('SELECT count(*),sum(distance_km) FROM observed_training').fetchone()
        self.assertEqual(row[:],(2,17))
        self.assertIsNone(self.db.execute("SELECT training_load FROM observed_training WHERE activity_id='456'").fetchone()[0])

    def test_seconds_and_units(self):
        self.assertEqual(tracking.seconds('1:21:55'),4915)
        self.assertEqual(tracking.fmt_pace(298.19),'4:58')


if __name__=='__main__':
    unittest.main()
