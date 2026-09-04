# Bounded market-source discovery

Discovery was performed on 2026-08-26 (Asia/Taipei), limited to Dataset 8066 and one four-calendar-day request. The public endpoint returned HTTP 200 and `application/json; charset=utf-8` for `StartDate=115.08.22`, `EndDate=115.08.25`, `$top=1000`, `$skip=0`. It returned 317,239 bytes. The live data used ROC dates such as `115.08.25` and fields `交易日期`, `種類代碼`, `作物代號`, `作物名稱`, `市場代號`, `市場名稱`, `上價`, `中價`, `下價`, `平均價`, `交易量`.

The same endpoint with Gregorian dates (`2026.08.22`–`2026.08.25`) returned `[]`; the adapter therefore accepts caller-provided source dates and normalizes observed ROC dates to ISO. Pagination was not fully exhausted during discovery; bounded repeated-page detection is implemented and tested with fixtures.

Validated exact crop codes are recorded in `config/produce.yml`: fruit `A1,B2,811/812/813,I1/I3,P1/P2,R1/R4/R6,T1/T6,51,31,G3`; vegetable `FC1,FB1,LA2,LD1,LF1/LF2,LH1/LH2,SB1/SB2,SD1,SE1/SE2,FI2/FI3`. They were selected only from the observed public response; this is a configured watchlist, not a complete crop taxonomy.

Committed fixtures are sanitized, minimal, and fixture-only: successful rows, empty response, HTML response, missing-field, duplicate-page, and upstream-correction scenarios. No full upstream dump is committed. The implementation stores only normalized configured-watchlist rows; it records source metadata separately and does not include fetch time in the stable source-row hash.

Input SHA-256: `SPEC.md` `2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6`; `PLAN.md` `6614a7b2c7c8f63941ae0217cb6076287ad05d9bb741dfeb51c6af0d81d860bb`; `TASKS.md` before implementation `5d0f0d94558693b1e07764744f07600e0fbd4b041349de8fb5fc100368bd2c5d`; `WORK_ORDER.md` `30a7f5b29ee4197e666ff7db2303e71e962c1adaa3e5cd35ad0422664d8733d7`; visual reference `bd2ddaeb4a1ce1431d27ad5901310e0abd1a30a9cd8d8f4725f60f78a1b2e7dd`.

## Issue #44 Part B — bounded discovery attempt — 2026-09-04

### 1. 本次環境證據（S 級，關於封鎖本身）

2026-09-04 約 14:56 UTC，從本次規劃環境對 §1 列出的每個 host 執行 `curl -sS -o /dev/null -m 20 -w '%{http_code} %{content_type}\n' <url>`，實際結果如下（全部為 `CONNECT tunnel failed, response 403`）：

```
https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx?$top=1 -> curl: (56) CONNECT tunnel failed, response 403
https://data.gov.tw/dataset/7299 -> curl: (56) CONNECT tunnel failed, response 403
https://www.afa.gov.tw/cht/index.php?code=list&ids=1103 -> curl: (56) CONNECT tunnel failed, response 403
https://fae.moa.gov.tw/ -> curl: (56) CONNECT tunnel failed, response 403
https://efish.fa.gov.tw/efish/ -> curl: (56) CONNECT tunnel failed, response 403
https://www.fa.gov.tw/ -> curl: (56) CONNECT tunnel failed, response 403
https://data.moa.gov.tw/open_detail.aspx?id=039 -> curl: (56) CONNECT tunnel failed, response 403
https://ppg.naif.org.tw/ -> curl: (56) CONNECT tunnel failed, response 403
proxy status: recentRelayFailures kind=connect_rejected, detail="gateway answered 403 to CONNECT (policy denial or upstream failure)" for data.moa.gov.tw:443, data.gov.tw:443, www.afa.gov.tw:443, fae.moa.gov.tw:443 (and the remaining hosts above)
server-side WebFetch to www.afa.gov.tw / data.moa.gov.tw / data.gov.tw -> EGRESS_BLOCKED
```

Proxy 的 `recentRelayFailures` 同時記錄上述每個 host 的 `connect_rejected` 事件，時間與上述一致；伺服器端 WebFetch 對 `www.afa.gov.tw`／`data.moa.gov.tw`／`data.gov.tw` 三者也回報 `EGRESS_BLOCKED`。這是 Issue #44 第 0 節與第一則留言記錄的同一狀況，第三次發生。

同一組 probe 於 2026-09-04 17:10 UTC 由 supervisor 獨立重跑一次，八個 URL 全部回報相同的 `curl: (56) CONNECT tunnel failed, response 403`，proxy `recentRelayFailures` 亦新增 `2026-09-04T17:10:45.926Z`–`17:10:48.211Z` 區間、`kind=connect_rejected`、`detail="gateway answered 403 to CONNECT (policy denial or upstream failure)"` 的紀錄，涵蓋 `data.moa.gov.tw`、`data.gov.tw`、`www.afa.gov.tw`、`fae.moa.gov.tw`、`efish.fa.gov.tw`、`www.fa.gov.tw`、`ppg.naif.org.tw` 全部七個 host。兩次觀測互相印證，封鎖為環境常態而非單次瞬時失敗。

### 2. 候選來源表（全部 A／B 級，未一手讀取）

以下每一列的 URL 屬 A 級（官方網域，本身未被讀取，僅記錄其存在）；欄位清單、單位與更新狀態等描述屬 B 級，來自搜尋引擎摘要，**並未一手讀取確認**，因此標註「待查證」處在下表 probe 完成前不得視為事實。

| 對應 B-4 | 來源 | 等級 | 一次 bounded probe 應記錄 |
|---|---|---|---|
| Q6 | 農糧署「每月盛產農產品產地」：`https://data.gov.tw/dataset/8120`、`https://data.moa.gov.tw/open_detail.aspx?id=061`（搜尋摘要：欄位 類別／盛產月份／名稱／品種名稱／主要生產-縣市別／主要生產-鄉鎮市別；摘要另稱 2016 年後未更新，**待查證**） | A（URL）／B（欄位、更新狀態） | HTTP status、Content-Type、bytes、`類別` 欄位的**全部 distinct 值**、最新資料月份、SHA-256 |
| Q6 | AFA `https://www.afa.gov.tw/cht/index.php?code=list&ids=1103&mod_code=search` 的 `type` 選項全集 | A | 頁面 `種類` 選單全部 option label／value |
| Q7 | 漁業署「漁業月曆」`https://fa.gov.tw/list.php?subtheme=1813&theme=web_structure` | A（URL）／B（內容性質未知） | 是否為 (魚種 × 月份[× 縣市]) 結構化資料或僅敘述；授權條款 |
| Q7 | 農業部食農教育資訊整合平臺 `https://fae.moa.gov.tw/`（搜尋摘要：含水產「當季食材」敘述，如飛魚 3–7 月） | A／B | 是否有結構化欄位、是否含縣市、授權；**敘述性內容不得寫入正式 mapping（BC-7）** |
| Q1、Q4、Q5 | 漁產品交易行情：`https://data.gov.tw/dataset/7299`、`https://data.moa.gov.tw/open_detail.aspx?id=039`；市場站 `https://efish.fa.gov.tw/efish/`（搜尋摘要欄位：交易日期、品種代碼、魚貨名稱、市場名稱、上價、中價、下價、交易量、平均價；單位**未證**） | A／B | endpoint、分頁參數、日期格式、價格與交易量單位、市場代號與品種代碼格式（與 8066 三位數市場代號、作物代號是否碰撞） |
| Q2、Q4、Q5 | 毛豬交易行情：`https://data.gov.tw/dataset/7296`、`https://data.moa.gov.tw/open_detail.aspx?id=026`（搜尋摘要：交易日期、市場名稱、頭數、平均重量 公斤、平均價格 元/公斤；來源系統 `ppg.naif.org.tw`） | A／B | 同上；確認是否為 元/公斤 或 元/百公斤 |
| Q3、Q4 | 家禽交易行情（白肉雞／雞蛋）：`https://data.moa.gov.tw/open_detail.aspx?id=056`；畜產會 `https://www.naif.org.tw/` | A／B | 欄位、單位、授權（畜產會為財團法人，非主管機關 open data） |
| Q8 | 農業部畜牧處相關頁（搜尋摘要僅見「夏季蛋量自然減少」等敘述） | B | 是否存在任何官方「產期／產季」定義；預期：不存在（BC-2） |

### 3. 結論

本次仍未取得任何 S 級證據；Part B 的 live 切片（新類別 season adapter、行情 adapter）維持 blocked，需在具 `*.gov.tw` egress 的環境逐條完成上表 probe 後另開 work order。
