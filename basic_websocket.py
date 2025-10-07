import json
import threading
import time
import websocket
from typing import Callable, Dict, Set
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BasicWebSocket:
    def __init__(self, callback: Callable[[str, float, str], None], status_callback: Callable[[str, str], None]):
        """
        初始化 Basic WebSocket

        Args:
            callback: 價格更新callback, 接收 (symbol, price) 參數
            status_callback: 連線狀態callback, 接收 (exchange_name, status) e.g. ('binance','connected')
        """
        self.callback = callback
        self.status_callback = status_callback
        self.ws = None
        self.ws_thread = None
        self.is_running = False
        self.subscribed_symbols: Set[str] = set()
        self.last_prices: Dict[str, float] = {}  # 記錄上次價格，用於判斷是否變動
        self.reconnect_delay = 5  # 重連延遲（秒）
        self.exchange_name = None
        self.base_url = None
        

    def start(self):
        """啟動 WebSocket 連接"""
        if self.is_running:
            logger.debug("WebSocket 已經在運行中")
            return
            
        self.is_running = True
        self.ws_thread = threading.Thread(target=self._run, daemon=True)
        self.ws_thread.start()
        logger.debug(f"{self.exchange_name} WebSocket 已啟動")
        
    def stop(self):
        """停止 WebSocket 連接"""
        self.is_running = False
        self._disconnect()
        logger.warning(f"{self.exchange_name} WebSocket 已停止")
        
    def subscribe(self, symbol: str):
        """
        訂閱特定加密貨幣的價格更新
        symbol: ex. BTC or ETH
        """
        symbol = symbol.upper()
        if symbol not in self.subscribed_symbols:
            self.subscribed_symbols.add(symbol)
            logger.debug(f"已訂閱 {self.exchange_name} {symbol} 價格更新")
            
            try:
                self._subscribe(self.ws, symbol)
            except Exception:
                logger.debug(f"{self.exchange_name} ws 尚未就緒，訂閱將在連線建立後送出")
            logger.debug(f"已登錄 {self.exchange_name} {symbol} 訂閱（將在連線可用時發送）")

    def unsubscribe(self, symbol: str):
        """
        取消訂閱特定加密貨幣
        symbol: ex. BTC or ETH
        """
        symbol = symbol.upper()
        if symbol in self.subscribed_symbols:
            # 先從本地清單移除，若 WebSocket 仍然可用則嘗試發送取消訂閱
            self.subscribed_symbols.remove(symbol)
            logger.debug(f"已取消訂閱 {self.exchange_name} {symbol}")

            try:
                self._unsubscribe(self.ws, symbol)
                logger.debug(f"已取消 {self.exchange_name} {symbol} 訂閱（如連線可用已發送取消請求）")
            except Exception:
                logger.debug(f"{self.exchange_name} ws 尚未就緒，取消訂閱已從本地清單移除")
            
            # 清除該幣種的最後價格記錄
            if symbol in self.last_prices:
                del self.last_prices[symbol]

    def _disconnect(self):
        """斷開 WebSocket"""
        if self.ws:
            try:
                self.ws.close()
                
            except Exception:
                logger.exception("關閉 WebSocket 時發生錯誤")
            finally:
                # 清除本地 ws 參考，讓後續重連能正確建立新的 WebSocketApp
                self._emit_status('disconnected')
                self.ws = None

    def _subscribe(self, ws, symbol: str):
        """向 WebSocket 發送訂閱請求"""
        if not self.is_running:
            return

        subscribe_msg = self._creat_subscribe_msg(symbol, 'subscribe')

        if not ws:
            # 尚未建立 ws 連線，訂閱會在 on_open 裡送出
            logger.warning(f"_subscribe: ws 尚未就緒，延後發送 {symbol} 訂閱")
            return
        try:
            msg_text = json.dumps(subscribe_msg)
            logger.debug(f"_subscribe -> 將送出給 {self.exchange_name}: {msg_text}")
            ws.send(msg_text)
            logger.debug(f"已向 {self.exchange_name} WebSocket 發送訂閱請求: {symbol}USDT")
        except Exception:
            logger.exception(f"發送訂閱請求 {symbol}USDT 時發生錯誤")

    def _unsubscribe(self, ws, symbol: str):
        """向 WebSocket 發送取消訂閱請求"""
        if not self.is_running:
            return

        unsubscribe_msg = self._creat_subscribe_msg(symbol, 'unsubscribe')

        if not ws:
            logger.warning(f"_unsubscribe: ws 尚未就緒，無法發送取消訂閱 {symbol}")
            return
        try:
            ws.send(json.dumps(unsubscribe_msg))
            logger.debug(f"已向 {self.exchange_name} WebSocket 發送取消訂閱請求: {symbol}USDT")
        except Exception:
            logger.exception(f"發送取消訂閱請求 {symbol}USDT 時發生錯誤")

 
    def _creat_subscribe_msg(self, symbol: str, type: str):
        pass

    def _run(self):
        """主運行迴圈"""
        while self.is_running:
            try:
                if not self.subscribed_symbols:
                    logger.info(f"{self.exchange_name} 沒有訂閱的幣種，等待中...")
                    time.sleep(2)
                    continue

                url = self.base_url
                if not url:
                    time.sleep(2)
                    continue

                logger.info(f"正在連接 {self.exchange_name} WebSocket: {url}")
                self._emit_status('connecting')

                self.ws = websocket._app.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_ping=self._on_ping,
                )
                
                # 運行 WebSocket（這會阻塞直到連接關閉）
                self.ws.run_forever()
                
                # 如果還在運行中，等待後重連
                if self.is_running:
                    logger.warning(f"{self.exchange_name} WebSocket 已斷開，{self.reconnect_delay} 秒後重連...")
                    time.sleep(self.reconnect_delay)
                    
            except Exception as e:
                logger.error(f"{self.exchange_name} WebSocket 錯誤: {e}")
                if self.is_running:
                    time.sleep(self.reconnect_delay)

    def _on_open(self, ws):
        """WebSocket 連接建立時的callback"""
        logger.debug(f"{self.exchange_name} WebSocket 連接已建立")
        # 連線建立後，向交易所發送目前已登記的所有訂閱
        try:
            for symbol in list(self.subscribed_symbols):
                try:
                    self._subscribe(ws, symbol)
                except Exception:
                    logger.exception(f"向 {self.exchange_name} 發送訂閱 {symbol} 時發生錯誤")
            self._emit_status('connected')
        except Exception:
            logger.exception("在 on_open 處理訂閱時發生未預期錯誤")

    def _on_message(self, ws, message):
        pass

    def _on_error(self, ws, error):
        """WebSocket 錯誤時的callback"""
        self._emit_status('error')
        logger.error(f"{self.exchange_name} WebSocket 錯誤: {error}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 關閉時的callback"""
        # 不在此清空或取消本地訂閱清單；保留訂閱讓重連時能自動重新訂閱
        self._emit_status('disconnected')
        logger.warning(f"{self.exchange_name} WebSocket 已關閉 (代碼: {close_status_code}, 訊息: {close_msg})")

    def _on_ping(self, ws, message):
        """WebSocket 收到 ping 時的callback"""
        # 預設不回送應用層 pong（避免對期望傳輸層 ping/pong 的伺服器產生無效請求）
        logger.debug(f"收到 {self.exchange_name} WebSocket ping (略過應用層回覆) ")

    def _emit_status(self, status: str):
        try:
            if self.status_callback and self.exchange_name:
                self.status_callback(self.exchange_name, status)
                logger.debug(f"已發送 {self.exchange_name} 狀態: {status}")
        except Exception:
            logger.exception("發送狀態更新時發生錯誤")