import copy
import json
import pathlib
import tempfile
import unittest
from tpw.taipei_map import build_taipei_map, TaipeiMapError, validate_taipei_map, taipei_map_csv

class MapDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = pathlib.Path(self.tmp.name)
        path = self.root/'data/source-meta/2026-08-25.json'; path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'source_id':'moa_market_8066','source_url':'https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx','source_role':'authoritative_final','dataset_semantics':'wholesale_market_daily_transaction','requested_start':'2026-08-01','requested_end':'2026-08-25','retrieved_at':'2026-08-25T01:00:00+00:00','status':'success','http_status':200,'content_hash':'sha256:'+'a'*64}))
        self.items=[{'canonical_id':'cabbage','display_name':'甘藍','market_crop_codes':['LA2']}]
        self.registry={'markets':[{'market_code':c,'feed_market_name':n,'county_slug':'taipei-city','feed_source_id':'moa_market_8066'} for c,n in [('104','台北二'),('109','台北一')]]}
        from tpw.taipei_map_assets import load_taipei_map_assets
        self.geo, self.geometry, _ = load_taipei_map_assets(pathlib.Path(__file__).resolve().parents[2])
        self.pub={'requested_date':'2026-08-25','resolved_date':'2026-08-25','status':'complete'}
    def row(self,date,code,price,volume,hashchar='b'):
        return {'transaction_date':date,'market_code':code,'market_name':{'104':'台北二','109':'台北一'}[code],'crop_code':'LA2','crop_name_raw':'甘藍','canonical_id':'cabbage','source_id':'moa_market_8066','fetched_at':'2026-08-25T02:00:00+00:00','row_hash':'sha256:'+hashchar*64,'avg_price_twd_per_kg':price,'volume_kg':volume}
    def build(self,rows):
        return build_taipei_map(rows,'2026-08-25',self.pub,self.items,self.registry,lambda _: {'markets':[]},self.root,self.geo,self.geometry)
    def test_weighted_isolated_and_deterministic(self):
        rows=[self.row('2026-08-24','104',100,10),self.row('2026-08-25','104',200,30,'c'),self.row('2026-08-25','109',150,20,'d')]
        a=self.build(rows); b=self.build(list(reversed(rows))+[copy.deepcopy(rows[0])]); self.assertEqual(a,b); self.assertEqual(taipei_map_csv(a),taipei_map_csv(b))
        stat=next(s for s in a['statistics'] if s['market_code']=='104')['windows']['7d']; self.assertEqual(stat['price_twd_per_kg'],175); self.assertEqual(stat['coverage_days'],2); self.assertEqual(stat['status'],'insufficient')
        self.assertEqual(a['comparisons'][0]['absolute_gap'],50)
    def test_fixture_excluded_and_conflict_fails(self):
        row=self.row('2026-08-25','104',20,10); fixture=copy.deepcopy(row); fixture.update(fetched_at='fixture',avg_price_twd_per_kg=9999,row_hash='sha256:'+'e'*64)
        doc=self.build([row,fixture]); self.assertEqual(next(q for q in doc['quality']['by_date_market'] if q['date']=='2026-08-25' and q['market_code']=='104')['fixture'],1); self.assertEqual(doc['comparisons'][0]['price_104'],20)
        altered=copy.deepcopy(row); altered['row_hash']='sha256:'+'f'*64
        with self.assertRaises(TaipeiMapError): self.build([row,altered])
    def test_missing_zero_closure_and_comparison(self):
        zero=self.row('2026-08-24','104',0,10)
        traded=self.row('2026-08-25','104',20,10,'c')
        calendar=lambda _: {'markets':[{'market_code':'104','schedule_status':'scheduled_closed'}]}
        doc=build_taipei_map([zero,traded],'2026-08-25',self.pub,self.items,self.registry,calendar,self.root,self.geo,self.geometry)
        days=next(s['days'] for s in doc['series'] if s['market_code']=='104')
        self.assertEqual(days[-2]['observation_status'],'zero_price')
        self.assertIsNone(days[-2]['price_twd_per_kg']); self.assertTrue(days[-1]['calendar_conflict'])
        self.assertEqual(doc['comparisons'][0]['comparison_status'],'not_comparable')
        self.assertIsNone(doc['comparisons'][0]['absolute_gap'])
    def test_fixture_mode_requires_fixture_metadata_and_never_mixes_observed(self):
        fixture_path=self.root/'data/source-meta/fixture.json'
        fixture_path.write_text(json.dumps({'source_id':'moa_market_8066','source_url':'https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx','requested_start':'2026-08-01','requested_end':'2026-08-25','fetched_at':'fixture','status':'fixture','http_status':200,'content_hash':'sha256:'+'a'*64}))
        row=self.row('2026-08-25','104',20,10); row['fetched_at']='fixture'
        observed=self.row('2026-08-25','109',30,10,'c')
        doc=build_taipei_map([row,observed],'2026-08-25',self.pub,self.items,self.registry,lambda _: {'markets':[]},self.root,self.geo,self.geometry,'fixture')
        self.assertEqual(doc['comparisons'][0]['price_104'],20); self.assertIsNone(doc['comparisons'][0]['price_109'])
        self.assertIn('合成測試資料', taipei_map_csv(doc))
        with self.assertRaises(TaipeiMapError): validate_taipei_map(doc,'observed')
    def test_copied_hash_with_changed_value_fails(self):
        row=self.row('2026-08-25','104',20,10); changed=copy.deepcopy(row); changed['avg_price_twd_per_kg']=21
        with self.assertRaises(TaipeiMapError): self.build([row,changed])
    def test_source_runs_only_supports_observation(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        source=root/'data/source-runs/2026-10-21.json'; dest=self.root/'data/source-runs/2026-10-21.json'
        dest.parent.mkdir(parents=True); dest.write_bytes(source.read_bytes())
        row=self.row('2026-10-21','104',20,10)
        pub={'requested_date':'2026-10-21','resolved_date':'2026-10-21','status':'complete'}
        doc=build_taipei_map([row],'2026-10-21',pub,self.items,self.registry,lambda _: {'markets':[]},self.root,self.geo,self.geometry)
        self.assertEqual(doc['comparisons'][0]['price_104'],20)
        self.assertEqual(doc['inputs']['source_manifest_refs'][0]['path'],'data/source-runs/2026-10-21.json')
    def test_malformed_nested_geography_rejected(self):
        doc=self.build([self.row('2026-08-25','104',20,10)])
        doc['geography']['markets'][0]['extra_field']='bad'
        with self.assertRaises(TaipeiMapError): validate_taipei_map(doc)
    def test_validator_rejects_tampered_values_and_mode(self):
        doc=self.build([self.row('2026-08-25','104',20,10)]); doc['series'][0]['days'][-1]['price_twd_per_kg']=float('nan')
        with self.assertRaises(TaipeiMapError): validate_taipei_map(doc)
        with self.assertRaises(TaipeiMapError): validate_taipei_map(self.build([]),'fixture')
