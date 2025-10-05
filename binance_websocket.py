"""
Binance WebSocket 模組
用於連接 Binance WebSocket API 並接收加密貨幣即時價格
"""
import json
import threading
import time
import websocket
from typing import Callable, Dict, Set
import logging

from basic_websocket import BasicWebSocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BinanceWebSocket(BasicWebSocket):
    """Binance WebSocket 連接管理器"""

    def __init__(self, callback: Callable[[str, float, str], None]):
        super().__init__(callback)
        self.exchange_name = 'Binance'
        self.requires_reconnect_on_subscribe = True
                
    def _get_websocket_url(self):
        """
        生成 WebSocket URL
        """
        if not self.subscribed_symbols:
            return None
        
        # 對於多個交易對，使用組合串流
        streams = [f"{symbol.lower()}usdt@trade" for symbol in self.subscribed_symbols]
        
        if len(streams) == 1:
            return f"wss://stream.binance.com:9443/ws/{streams[0]}"
        else:
            # 多個串流使用組合格式
            return f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
                    
    def _subscribe(self, ws, symbol):
        pass
        
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
                        self.callback(symbol, price, 'Binance')
                        logger.debug(f"Binance {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")

    def _on_ping(self, ws, message):
        """Override ping handling for Binance: don't send application-level JSON pong.

        Binance uses transport-level ping/pong. Sending an application JSON pong
        can result in "Invalid request" and a 1008 close. Just log and return.
        """
        logger.debug("收到 Binance WebSocket ping — 使用 transport-level pong 回應 (略過應用層回復)")


# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    binance_ws = BinanceWebSocket(callback=test_callback)
    
    # 訂閱幣種
    binance_ws.subscribe("BTC")
    binance_ws.subscribe("ETH")
    
    # 啟動
    binance_ws.start()
    
    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        binance_ws.stop()
