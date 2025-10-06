import json
import threading
import time
import websocket
from typing import Callable, Dict, Set
from basic_websocket import BasicWebSocket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BybitWebSocket(BasicWebSocket):
    def __init__(self, callback: Callable[[str, float, str], None]):
        super().__init__(callback)
        self.base_url = "wss://stream.bybit.com/v5/public/spot"
        self.exchange_name = 'Bybit'
        self.requires_reconnect_on_subscribe = False
    
    def _get_websocket_url(self):
        return "wss://stream.bybit.com/v5/public/spot"
        
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
            # Bybit trade stream 格式            
            if 's' in data and 'p' in data:
                symbol_full = data['s']  # ex. BTCUSDT
                if symbol_full.endswith('USDT'):
                    symbol = symbol_full[:-4]  #  BTC
                    price = float(data['p'])
                    
                    # 只有當價格變動時才 callback
                    if symbol not in self.last_prices or self.last_prices[symbol] != price:
                        self.last_prices[symbol] = price
                        self.callback(symbol, price, 'bybit')
                        logger.debug(f"Bybit {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")

    def _creat_subscribe_msg(self, symbol: str, type: str):
        """生成 Bybit 訂閱訊息"""
        return {
            "op": type,
            "args": [
                f"publicTrade.{symbol}USDT"
            ]
        }

    def _on_ping(self, ws, message): # TODO: Initiative ping if needed
        """WebSocket 收到 ping 時的callback"""
        logger.debug("收到 Bybit WebSocket ping")
        try:
            if ws:
                ws.send(json.dumps({
                    "success": True,
                    "ret_msg": "pong",
                    "conn_id": "0970e817-426e-429a-a679-ff7f55e0b16a",
                    "op": "ping"
                }))
        except Exception:
            logger.exception("回覆 ping 時發生錯誤")
        
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 關閉時的callback"""
        logger.info(f"Bybit WebSocket 已關閉 (代碼: {close_status_code}, 訊息: {close_msg})")


# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    bybit_ws = BybitWebSocket(callback=test_callback)
    
    # 啟動
    bybit_ws.start()

    # 訂閱幣種
    bybit_ws.subscribe("BTC")
    bybit_ws.subscribe("ETH")

    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        bybit_ws.stop()
