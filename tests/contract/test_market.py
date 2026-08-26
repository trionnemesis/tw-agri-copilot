import io, unittest
from tpw.market import fetch
class Response:
 def __init__(self, body, content_type="application/json"): self._body=body; self.headers={"Content-Type":content_type}; self.status=200
 def read(self): return self._body
class MarketContractTest(unittest.TestCase):
 def test_html_and_empty_fail_before_promotion(self):
  for body,ct in [(b"<html>x</html>","text/html"),(b"", "application/json")]:
   with self.assertRaises(ValueError): fetch("115.08.25","115.08.25",opener=lambda *_a,**_k:Response(body,ct))
 def test_duplicate_page_fails(self):
  body='[{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉","市場代號":"1","市場名稱":"X","平均價":1,"交易量":1}]'.encode()
  with self.assertRaises(ValueError): fetch("115.08.25","115.08.25",top=1,max_pages=2,opener=lambda *_a,**_k:Response(body))
 def test_malformed_status_and_url_pagination(self):
  good='[{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉","市場代號":"1","市場名稱":"X","平均價":1,"交易量":1}]'.encode(); urls=[]
  self.assertEqual(len(fetch('115.08.25','115.08.25',top=2,opener=lambda *_a,**_k:Response(good),urls=urls)),1); self.assertIn('%24skip=0',urls[0])
  with self.assertRaises(ValueError): fetch('115.08.25','115.08.25',opener=lambda *_a,**_k:Response(b'{bad'))
