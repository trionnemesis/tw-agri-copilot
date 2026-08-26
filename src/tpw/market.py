import hashlib, json, urllib.parse, urllib.request
from .model import REQUIRED
URL = "https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx"
def fetch(start, end, top=1000, max_pages=20, opener=urllib.request.urlopen, urls=None):
    all_rows, page_hashes = [], set()
    for page in range(max_pages):
        query = urllib.parse.urlencode({"StartDate":start,"EndDate":end,"$top":top,"$skip":page*top})
        url = URL + "?" + query
        if urls is not None: urls.append(url)
        response = opener(url, timeout=30)
        content_type = response.headers.get("Content-Type", "")
        body = response.read()
        if getattr(response, "status", 200) != 200 or "json" not in content_type.lower(): raise ValueError("upstream response is not successful JSON")
        if not body.strip() or body.lstrip().startswith(b"<"): raise ValueError("upstream response is empty or HTML")
        try: rows = json.loads(body)
        except json.JSONDecodeError as e: raise ValueError("upstream response is malformed JSON") from e
        if not isinstance(rows, list): raise ValueError("upstream JSON must be a collection")
        if rows and any(not all(k in r for k in REQUIRED) for r in rows): raise ValueError("upstream row missing required fields")
        digest = hashlib.sha256(body).hexdigest()
        if rows and digest in page_hashes: raise ValueError("duplicate pagination page")
        page_hashes.add(digest); all_rows.extend(rows)
        if len(rows) < top: break
    else: raise ValueError("maximum pages reached")
    if not all_rows: raise ValueError("upstream returned no rows")
    return all_rows
