import unittest
from tpw.model import iso_date, normalize, canonical_map, upsert
from tpw.analytics import aggregate
class ModelTest(unittest.TestCase):
 def test_roc_and_weighted_average(self):
  self.assertEqual(iso_date("115.08.25"),"2026-08-25")
  mapping=canonical_map([{"canonical_id":"banana","display_name":"香蕉","category":"fruit","enabled":True,"market_crop_codes":["A1"]}])
  raw=[{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉","市場代號":"a","市場名稱":"A","平均價":20,"交易量":1000},{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉","市場代號":"b","市場名稱":"B","平均價":40,"交易量":10}]
  rows=[normalize(x,mapping) for x in raw]; self.assertAlmostEqual(aggregate(rows)[0]["weighted_avg_price_twd_per_kg"],20.19801980198)
 def test_correction_upsert_replaces_key(self):
  mapping=canonical_map([{"canonical_id":"banana","display_name":"香蕉","category":"fruit","enabled":True,"market_crop_codes":["A1"]}]); a={"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉","市場代號":"a","市場名稱":"A","平均價":20,"交易量":1}; b=dict(a,平均價=21)
  self.assertEqual(len(upsert([normalize(a,mapping),normalize(b,mapping)])),1)
 def test_hash_ignores_fetch_time_and_numeric_errors(self):
  mapping=canonical_map([{"canonical_id":"banana","display_name":"香蕉","category":"fruit","enabled":True,"market_crop_codes":["A1"]}]); a={"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉","市場代號":"a","市場名稱":"A","平均價":20,"交易量":1}
  self.assertEqual(normalize(a,mapping,'first')['row_hash'],normalize(a,mapping,'second')['row_hash'])
  with self.assertRaises(ValueError): normalize(dict(a,平均價='NaN'),mapping)
