# 臺北批發地圖：地理證據

2026-10-29 下載臺北市政府開放資料原始資源，保存在 `data/geography/taipei/`；日常建置不連線下載。資料以臺北市政府資料開放授權條款第 1 版授權，請註明資料來源。來源與輸出 SHA-256、原始 WKT、轉換與署名記錄於兩個 geography 配置檔。

- [臺北市區界圖](https://data.taipei/dataset/detail?id=1601ef3a-c253-4988-b047-943d9e786143)：民政局 SHP，十二筆行政區。原始 `.prj` 為 TWD97 TM2、中央經線 121°、false easting 250000 m，對應 EPSG:3826；不能僅由「TWD97」推斷。輸出保留此投影，單一等比例 affine transform 加 Y 軸反轉，無個別邊界線簡化；顯示座標四捨五入至 1 SVG 單位（約 37.4 m），相鄰重複點移除。未簡化原始幾何仍保存在 ZIP。更新可執行 `python3 tools/generate_taipei_svg.py` 並比對 source/output hash。
- [臺北市批發市場 CSV](https://data.taipei/dataset/detail?id=4a50dd4a-b09c-47c8-9374-fc04a9e59cc9)：CP950 編碼，座標欄 longitude／latitude，來源描述「座標(84)」。第二果菜批發市場的民族東路 336 號、121.537226／25.068013 與 [北農聯絡頁](https://www.tapmc.com.tw/Pages/ContactUs)地址一致；以 104 精確對應，核對日為 2026-10-29，不推斷歷史有效區間。
- 第一果菜批發市場 CSV 為萬大路 533 號、121.490125／25.034179；[市府 FAQ](https://www.gov.taipei/News_Content.aspx?n=EEC70A4186D4C828&s=7D70CF7492A6DFF5&sms=87415A8B9CE81B16) 指農產中繼拍賣／零批場為 531 號。533 座標僅作 reference_site、conflicting_sources，不畫成營運點。FAQ 的預計搬遷日期不代表實際搬遷。109 行情仍可使用，精確營運座標及實際遷移日期尚待查證。

原始 CSV 的魚市 531 號座標不能代替第一果菜中繼拍賣場的精確座標。兩個地點均非產地。若更新來源，需重新驗證每個地址、點位及有效時間，並人工審查邊界和定位；不能透過更改 hash 單獨宣稱完成查核。
