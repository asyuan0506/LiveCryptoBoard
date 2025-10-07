"""
Bitget WebSocket 模組
用於連接 Bitget WebSocket API 並接收加密貨幣即時價格
Highly recommend you to subscribe less than 50 channels in one connection
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


class BitgetWebSocket(BasicWebSocket):
    def __init__(self, callback: Callable[[str, float, str], None]):
        super().__init__(callback)
        self.exchange_name = 'Bitget'
        self.requires_reconnect_on_subscribe = False
        
    def _get_websocket_url(self):
        return "wss://ws.bitget.com/v2/ws/public"
    
    def _creat_subscribe_msg(self, symbol: str, type: str):
        """生成 Bitget 訂閱訊息"""
        return {
            "op": type,
            "args": [{
                "instType":"SPOT",
                "channel":"trade",
                "instId":f"{symbol}USDT"
            },]
        }  
        
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
            if "data" in data and "arg" in data:
                # Bitget trade stream 格式    
                if "instId" in data["arg"] and "price" in data["data"][0]:        
                    symbol_full = data["arg"]["instId"]  # ex. BTCUSDT
                    if symbol_full.endswith('USDT'):
                        symbol = symbol_full[:-4]  #  BTC
                        price = float(data["data"][0]["price"])

                        # 只有當價格變動時才 callback
                        if symbol not in self.last_prices or self.last_prices[symbol] != price:
                            self.last_prices[symbol] = price
                            self.callback(symbol, price, 'bitget') 
                            logger.debug(f"Bitget {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            if "pong" in message:
                logger.debug("收到 Bitget WebSocket pong")
            else:
                logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")
            
    def _on_ping(self, ws, message):
        """WebSocket 收到 ping 時的callback"""
        """Bitget 不會主動發送 ping"""
    
    def _initiate_ping(self):
        """啟動定期發送 ping"""
        while self.is_running and self.ws:
            try:
                self.ws.send("ping")
                logger.debug("已向 Bitget WebSocket 發送 ping")
            except Exception as e:
                logger.error(f"發送 ping 時發生錯誤: {e}")
            time.sleep(30)  # 每 30 秒發送一次 ping

# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    bitget_ws = BitgetWebSocket(callback=test_callback)
    
    # 啟動
    bitget_ws.start()

    # 訂閱幣種
    bitget_ws.subscribe("BTC")
    bitget_ws.subscribe("ETH")

    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        bitget_ws.stop()
