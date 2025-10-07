import json
import time
from typing import Callable
from basic_websocket import BasicWebSocket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BinanceWebSocket(BasicWebSocket):
    def __init__(self, callback: Callable[[str, float, str], None], status_callback: Callable[[str, str], None]):
        super().__init__(callback, status_callback)
        self.exchange_name = 'Binance'
        self.base_url = "wss://stream.binance.com:9443/ws"
      
    def _on_message(self, ws, message):
        """
        接收到 WebSocket 訊息時的callback
        
        Args:
            ws: WebSocket 物件
            message: 接收到的訊息
        """
        try:
            data = json.loads(message)
            # 處理組合串流格式
            if 'stream' in data:
                data = data['data']
            
            # Binance trade stream 格式
            if 's' in data and 'p' in data:
                symbol_full = data['s']  # ex. BTCUSDT
                if symbol_full.endswith('USDT'):
                    symbol = symbol_full[:-4]  #  BTC
                    price = float(data['p'])
                    
                    # 只有當價格變動時才 callback
                    if symbol not in self.last_prices or self.last_prices[symbol] != price:
                        self.last_prices[symbol] = price
                        self.callback(symbol, price, 'binance')
                        logger.debug(f"Binance {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")

    def _creat_subscribe_msg(self, symbol: str, type: str):
        """生成 Binance 訂閱訊息"""
        return {
            "method": type.upper(),
            "params":
            [
            f"{symbol.lower()}usdt@trade",
            ],
            "id": time.time_ns() % (10 ** 8)
        }

# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    binance_ws = BinanceWebSocket(callback=test_callback, status_callback=lambda ex, st: print(f"[狀態] {ex}: {st}"))
    
    # 啟動
    binance_ws.start()

    # 訂閱幣種
    binance_ws.subscribe("BTC")
    binance_ws.subscribe("ETH")

    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        binance_ws.stop()
