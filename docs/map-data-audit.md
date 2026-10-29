# 臺北地圖資料稽核

基準 `f5e20443edb3687d7d0d3872c544132926c39381`；稽核 committed `data/market/daily` 與 `data/source-meta`，不重新下載上游資料。日期截至 2026-10-21，requested 2026-10-29，publication 為 `source_unavailable`。選擇 8066、104/109 及設定中的原始作物代碼；各筆依 fixture 標記、來源時間、權威角色與成功 metadata 日期範圍檢查。數字是這個快照，不是上游全量或永久覆蓋率。

| 範圍 | 可追溯 observed | fixture 排除 | provenance_unknown 排除 |
|---|---:|---:|---:|
| 全部 committed 歷史 | 2,368 | 1,327 | 119 |
| 90 日窗 2026-07-24–10-21 | 2,368 | 1,247 | 119 |
| 全歷史：104 | 1,165 | 663 | 59 |
| 全歷史：109 | 1,203 | 664 | 60 |

Observed 涵蓋 43 個交易日期（2026-08-26–10-21）；fixture 涵蓋 35 日（2026-07-22–08-25）；unknown 出現於 08-23、08-25，列具有時間戳但未找到符合正式資格的成功 ingestion metadata。90 日窗可追溯列無零價或零量；截至日可比較的同 raw code 有 26 個。按日期與市場的完整計數和原因由 map payload 的 `quality.by_date_market` 輸出。

來源 metadata 為 ingestion 範圍關聯，並非逐列原始 bytes 包含證明；`raw_replay_available=false`。來源列抓取時間不必等於 manifest 時間。較舊 Taipei/global 統計未套用這個排除規則，且以 canonical 合併品種；不得直接比較為同一統計口徑。歷史修正須另立工作，不在地圖功能靜默改寫。
