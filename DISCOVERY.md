# Bounded market-source discovery

Discovery was performed on 2026-08-26 (Asia/Taipei), limited to Dataset 8066 and one four-calendar-day request. The public endpoint returned HTTP 200 and `application/json; charset=utf-8` for `StartDate=115.08.22`, `EndDate=115.08.25`, `$top=1000`, `$skip=0`. It returned 317,239 bytes. The live data used ROC dates such as `115.08.25` and fields `交易日期`, `種類代碼`, `作物代號`, `作物名稱`, `市場代號`, `市場名稱`, `上價`, `中價`, `下價`, `平均價`, `交易量`.

The same endpoint with Gregorian dates (`2026.08.22`–`2026.08.25`) returned `[]`; the adapter therefore accepts caller-provided source dates and normalizes observed ROC dates to ISO. Pagination was not fully exhausted during discovery; bounded repeated-page detection is implemented and tested with fixtures.

Validated exact crop codes are recorded in `config/produce.yml`: fruit `A1,B2,811/812/813,I1/I3,P1/P2,R1/R4/R6,T1/T6,51,31,G3`; vegetable `FC1,FB1,LA2,LD1,LF1/LF2,LH1/LH2,SB1/SB2,SD1,SE1/SE2,FI2/FI3`. They were selected only from the observed public response; this is a configured watchlist, not a complete crop taxonomy.

Committed fixtures are sanitized, minimal, and fixture-only: successful rows, empty response, HTML response, missing-field, duplicate-page, and upstream-correction scenarios. No full upstream dump is committed. The implementation stores only normalized configured-watchlist rows; it records source metadata separately and does not include fetch time in the stable source-row hash.

Input SHA-256: `SPEC.md` `2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6`; `PLAN.md` `6614a7b2c7c8f63941ae0217cb6076287ad05d9bb741dfeb51c6af0d81d860bb`; `TASKS.md` before implementation `5d0f0d94558693b1e07764744f07600e0fbd4b041349de8fb5fc100368bd2c5d`; `WORK_ORDER.md` `30a7f5b29ee4197e666ff7db2303e71e962c1adaa3e5cd35ad0422664d8733d7`; visual reference `bd2ddaeb4a1ce1431d27ad5901310e0abd1a30a9cd8d8f4725f60f78a1b2e7dd`.
