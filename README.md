# Live Crypto Board - 即時加密貨幣價格看板

## 專案簡介
Live Crypto Board 是一個基於 Flask 與 WebSocket 的即時加密貨幣價格追蹤系統。本專案透過 WebSocket 同步串接多家知名交易所（包括 Binance, Bybit, Coinbase, OKX, Bitget）的即時成交資料，讓使用者能夠在單一介面上同時比較不同交易所的最新價格。

## 核心功能
* **多交易所串接**：整合五大交易所的 WebSocket API，即時獲取報價。
* **即時動態更新**：採用 Flask-SocketIO 實現前端與後端的雙向溝通。
* **價格差異視覺化**：自動標註各交易所間的最高價與最低價，協助使用者識別潛在的價差。
* **多幣種支持**：預設支援 BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC 等熱門幣種，並提供搜尋功能以查看更多代幣。

## 更多資訊
若想進一步了解本專案的開發細節、架構設計與心得，歡迎查看我們的完整簡報：

👉 [Live Crypto Board 專案簡報 (Canva)](https://www.canva.com/design/DAG0_0II4UI/egtKLTJKR0k624fnX6RPPA/edit?utm_content=DAG0_0II4UI&utm_campaign=designshare&utm_medium=link2&utm_source=sharebutton)
