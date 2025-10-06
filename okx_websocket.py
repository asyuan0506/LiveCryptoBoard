import json
import threading
import time
import websocket
from typing import Callable, Dict, Set
from basic_websocket import BasicWebSocket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OkxWebSocket(BasicWebSocket):
    def __init__(self, callback: Callable[[str, float, str], None]):
        super().__init__(callback)
        self.base_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.exchange_name = 'OKX'
        self.requires_reconnect_on_subscribe = False
        
    def _get_websocket_url(self):
        return "wss://ws.okx.com:8443/ws/v5/public"
      
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
            if 'data' in data:
                data = data['data'][0]
            # OKX trade stream 格式            
            if 'instId' in data and 'px' in data:
                symbol_full = data['instId']  # ex. BTC-USDT
                if symbol_full.endswith('USDT'):
                    symbol = symbol_full[:-5]  #  BTC
                    price = float(data['px'])

                    # 只有當價格變動時才 callback
                    if symbol not in self.last_prices or self.last_prices[symbol] != price:
                        self.last_prices[symbol] = price
                        self.callback(symbol, price, 'okx')
                        logger.debug(f"OKX {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")

    def _creat_subscribe_msg(self, symbol: str, type: str):
        """生成 OKX 訂閱訊息"""
        return {
            "op": type,
            "args": [
                {"channel": "trades", 
                 "instId": f"{symbol}-USDT"}
            ]
        }
    def _on_ping(self, ws, message):
        """WebSocket 收到 ping 時的callback"""
        logger.debug("收到 OKX WebSocket ping")
        try:
            if ws:
                ws.send(json.dumps({
                    "op": "pong"
                }))
        except Exception:
            logger.exception("回覆 pong 時發生錯誤")

# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    okx_ws = OkxWebSocket(callback=test_callback)
    
    # 啟動
    okx_ws.start()

    # 訂閱幣種
    okx_ws.subscribe("BTC")
    okx_ws.subscribe("ETH")

    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        okx_ws.stop()
