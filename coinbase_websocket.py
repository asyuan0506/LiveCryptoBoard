import json
import threading
import time
import websocket
from typing import Callable, Dict, Set
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CoinbaseWebSocket:
    def __init__(self, callback: Callable[[str, float, str], None]):
        """
        初始化 Coinbase WebSocket

        Args:
            callback: 價格更新回調函數，接收 (symbol, price) 參數
        """
        self.base_url = "wss://ws-feed.exchange.coinbase.com"
        self.callback = callback
        self.ws = None
        self.ws_thread = None
        self.is_running = False
        self.subscribed_symbols: Set[str] = set()
        self.last_prices: Dict[str, float] = {}  # 記錄上次價格，用於判斷是否變動
        self.reconnect_delay = 5  # 重連延遲（秒）
        
    def start(self):
        """啟動 WebSocket 連接"""
        if self.is_running:
            logger.warning("WebSocket 已經在運行中")
            return
            
        self.is_running = True
        self.ws_thread = threading.Thread(target=self._run, daemon=True)
        self.ws_thread.start()
        logger.info("Coinbase WebSocket 已啟動")
        
    def stop(self):
        """停止 WebSocket 連接"""
        self.is_running = False
        self._disconnect()
        logger.info("Coinbase WebSocket 已停止")
        
    def subscribe(self, symbol: str):
        """
        訂閱特定加密貨幣的價格更新
        symbol: ex. BTC or ETH
        """
        symbol = symbol.upper()
        if symbol not in self.subscribed_symbols:
            self.subscribed_symbols.add(symbol)
            # 如果連線尚未建立，會在 _on_open 時一次性訂閱所有已登記的幣種
            try:
                self._subscribe(self.ws, symbol)
            except Exception:
                logger.debug("Coinbase ws 尚未就緒，訂閱將在連線建立後送出")
            logger.info(f"已登錄 Coinbase {symbol} 訂閱（將在連線可用時發送）")
            
                
    def unsubscribe(self, symbol: str):
        """
        取消訂閱特定加密貨幣
        symbol: ex. BTC or ETH
        """
        symbol = symbol.upper()
        if symbol in self.subscribed_symbols:
            # 先從本地清單移除，若 WebSocket 仍然可用則嘗試發送取消訂閱
            self.subscribed_symbols.remove(symbol)
            try:
                self._unsubscribe(self.ws, symbol)
                logger.info(f"已取消 Coinbase {symbol} 訂閱（如連線可用已發送取消請求）")
            except Exception:
                logger.debug("Coinbase ws 尚未就緒，取消訂閱已從本地清單移除")
            
            # 清除該幣種的最後價格記錄
            if symbol in self.last_prices:
                del self.last_prices[symbol]
            
            if self.ws and self.is_running:
                self._disconnect()
                
            
    def _disconnect(self):
        """斷開 WebSocket"""
        if self.ws:
            self.ws.close()
        
    def _run(self):
        """主運行迴圈"""
        while self.is_running:
            try:
                if not self.subscribed_symbols:
                    logger.info("沒有訂閱的幣種，等待中...")
                    time.sleep(2)
                    continue

                logger.info(f"正在連接 Coinbase WebSocket: {self.base_url}")
                
                self.ws = websocket._app.WebSocketApp(
                    self.base_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_ping=self._on_ping,
                    on_open=self._on_open
                )
                
                # 運行 WebSocket（這會阻塞直到連接關閉）
                self.ws.run_forever()
                
                # 如果還在運行中，等待後重連
                if self.is_running:
                    logger.info(f"WebSocket 已斷開，{self.reconnect_delay} 秒後重連...")
                    time.sleep(self.reconnect_delay)
                    
            except Exception as e:
                logger.error(f"Coinbase WebSocket 錯誤: {e}")
                if self.is_running:
                    time.sleep(self.reconnect_delay)
                    
    def _on_open(self, ws):
        """WebSocket 連接建立時的callback"""
        logger.info("Coinbase WebSocket 連接已建立")
        # 連線建立後，向 Coinbase 發送目前已登記的所有訂閱
        try:
            for symbol in list(self.subscribed_symbols):
                try:
                    self._subscribe(ws, symbol)
                except Exception:
                    logger.exception(f"向 Coinbase 發送訂閱 {symbol} 時發生錯誤")
        except Exception:
            logger.exception("在 on_open 處理訂閱時發生未預期錯誤")
        
    def _on_message(self, ws, message):
        """
        接收到 WebSocket 訊息時的callback
        
        Args:
            ws: WebSocket 物件
            message: 接收到的訊息
        """
        try:
            data = json.loads(message)
            # Coinbase trade stream 格式            
            if 'product_id' in data and 'price' in data:
                symbol_full = data['product_id']  # ex. BTC-USDT
                if symbol_full.endswith('USDT'):
                    symbol = symbol_full[:-5]  #  BTC
                    price = float(data['price'])
                    # 只有當價格變動時才 callback
                    if symbol not in self.last_prices or self.last_prices[symbol] != price:
                        self.last_prices[symbol] = price
                        self.callback(symbol, price, 'Coinbase')
                        logger.debug(f"Coinbase {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")

    def _subscribe(self, ws, symbol: str):
        """向 Coinbase WebSocket 發送訂閱請求"""
        if not self.is_running:
            return

        subscribe_msg = {
            "type": "subscribe",
            "product_ids": [
                f"{symbol}-USDT"
            ],
            "channels": ["ticker"]
        }
        if not ws:
            # 尚未建立 ws 連線，訂閱會在 on_open 裡送出
            logger.debug(f"_subscribe: ws 尚未就緒，延後發送 {symbol} 訂閱")
            return
        try:
            ws.send(json.dumps(subscribe_msg))
            logger.info(f"已向 Coinbase WebSocket 發送訂閱請求: {symbol}USDT")
        except Exception:
            logger.exception(f"發送訂閱請求 {symbol}USDT 時發生錯誤")

    def _unsubscribe(self, ws, symbol: str):
        """向 Coinbase WebSocket 發送取消訂閱請求"""
        if not self.is_running:
            return

        unsubscribe_msg = {
            "type": "unsubscribe",
            "product_ids": [
                f"{symbol}-USDT"
            ],
            "channels": ["ticker"]
        }
        if not ws:
            logger.debug(f"_unsubscribe: ws 尚未就緒，無法發送取消訂閱 {symbol}")
            return
        try:
            ws.send(json.dumps(unsubscribe_msg))
            logger.info(f"已向 Coinbase WebSocket 發送取消訂閱請求: {symbol}USDT")
        except Exception:
            logger.exception(f"發送取消訂閱請求 {symbol}USDT 時發生錯誤")
            
    def _on_error(self, ws, error):
        """WebSocket 錯誤時的callback"""
        logger.error(f"Coinbase WebSocket 錯誤: {error}")

    def _on_ping(self, ws, message):
        """WebSocket 收到 ping 時的callback"""
        logger.debug("收到 Coinbase WebSocket ping")
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
        for symbol in list(self.subscribed_symbols):
            self.unsubscribe(symbol)
        logger.info(f"Coinbase WebSocket 已關閉 (代碼: {close_status_code}, 訊息: {close_msg})")


# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float, exchange: str):
        print(f"[測試] {symbol}: ${price:,.2f} (來自: {exchange})")

    # 建立 WebSocket 實例
    Coinbase_ws = CoinbaseWebSocket(callback=test_callback)
    
    # 啟動
    Coinbase_ws.start()

    # 訂閱幣種
    Coinbase_ws.subscribe("BTC")
    Coinbase_ws.subscribe("ETH")

    try:
        # 保持運行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        Coinbase_ws.stop()
