import json
import time
from typing import Callable
from basic_websocket import BasicWebSocket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CoinbaseWebSocket(BasicWebSocket):
    def __init__(self, callback: Callable[[str, float, str], None], status_callback: Callable[[str, str], None]):
        super().__init__(callback, status_callback)
        self.exchange_name = 'Coinbase'
        self.base_url = "wss://ws-feed.exchange.coinbase.com"
        
    def _on_message(self, ws, message):
        """
        接收到 WebSocket 訊息時的callback
        
        Args:
            ws: WebSocket 物件
            message: 接收到的訊息
        """
        try:
            data = json.loads(message)
            # 記錄並處理 Coinbase 的 ticker 訊息
            # Coinbase product_id 形如 'BTC-USD' 或 'BTC-USDC' 等，用 '-' 分割較保險
            if 'product_id' in data and 'price' in data:
                symbol_full = data['product_id']  # ex. BTC-USDT
                if symbol_full.endswith('USDT'):
                    symbol = symbol_full[:-5]  #  BTC
                    price = float(data['price'])
                    # 只有當價格變動時才 callback
                    if symbol not in self.last_prices or self.last_prices[symbol] != price:
                        self.last_prices[symbol] = price
                        self.callback(symbol, price, 'coinbase')
                        logger.debug(f"Coinbase {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")

    def _creat_subscribe_msg(self, symbol: str, type: str):
        """生成 Coinbase 訂閱訊息"""
        # 使用 USD 為 Coinbase 的主要報價對 (Coinbase 常用 -USD/-USDC，而非 -USDT)
        # 使用 dict 形式的 channels 更明確，兼容 Coinbase 的多種訂閱格式
        return {
            "type": type,
            "product_ids": [
                f"{symbol}-USDT"
            ],
            "channels": ["ticker"]
        }
    
# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    coinbase_ws = CoinbaseWebSocket(callback=test_callback, status_callback=lambda ex, st: print(f"[狀態] {ex}: {st}"))
    
    # 啟動
    coinbase_ws.start()

    # 訂閱幣種
    coinbase_ws.subscribe("BTC")
    coinbase_ws.subscribe("ETH")

    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        coinbase_ws.stop()
