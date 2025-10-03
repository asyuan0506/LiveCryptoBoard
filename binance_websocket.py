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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BinanceWebSocket:
    """Binance WebSocket 連接管理器"""
    
    def __init__(self, callback: Callable[[str, float], None]):
        """
        初始化 Binance WebSocket
        
        Args:
            callback: 價格更新回調函數，接收 (symbol, price) 參數
        """
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
        logger.info("Binance WebSocket 已啟動")
        
    def stop(self):
        """停止 WebSocket 連接"""
        self.is_running = False
        self._disconnect()
        logger.info("Binance WebSocket 已停止")
        
    def subscribe(self, symbol: str):
        """
        訂閱特定加密貨幣的價格更新
        symbol: ex. BTC or ETH
        """
        symbol = symbol.upper()
        if symbol not in self.subscribed_symbols:
            self.subscribed_symbols.add(symbol)
            logger.info(f"已訂閱 Binance {symbol} 價格更新")
            
            # 如果 WebSocket 已連接，重新建立連接以訂閱新的幣種(is_running 還是 True 會重連)
            if self.ws and self.is_running:
                self._disconnect()
                
    def unsubscribe(self, symbol: str):
        """
        取消訂閱特定加密貨幣
        symbol: ex. BTC or ETH
        """
        symbol = symbol.upper()
        if symbol in self.subscribed_symbols:
            self.subscribed_symbols.remove(symbol)
            logger.info(f"已取消訂閱 Binance {symbol}")
            
            # 清除該幣種的最後價格記錄
            if symbol in self.last_prices:
                del self.last_prices[symbol]
            
            if self.ws and self.is_running:
                self._disconnect()
                
    def _get_websocket_url(self) :
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
                    
                url = self._get_websocket_url()
                if not url:
                    time.sleep(2)
                    continue
                    
                logger.info(f"正在連接 Binance WebSocket: {url}")
                
                self.ws = websocket._app.WebSocketApp(
                    url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open
                )
                
                # 運行 WebSocket（這會阻塞直到連接關閉）
                self.ws.run_forever()
                
                # 如果還在運行中，等待後重連
                if self.is_running:
                    logger.info(f"WebSocket 已斷開，{self.reconnect_delay} 秒後重連...")
                    time.sleep(self.reconnect_delay)
                    
            except Exception as e:
                logger.error(f"Binance WebSocket 錯誤: {e}")
                if self.is_running:
                    time.sleep(self.reconnect_delay)
                    
    def _on_open(self, ws):
        """WebSocket 連接建立時的callback"""
        logger.info("Binance WebSocket 連接已建立")
        
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
                        self.callback(symbol, price)
                        logger.debug(f"Binance {symbol} 價格更新: ${price:,.2f}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析錯誤: {e}")
        except Exception as e:
            logger.error(f"處理訊息時發生錯誤: {e}")
            
    def _on_error(self, ws, error):
        """WebSocket 錯誤時的callback"""
        logger.error(f"Binance WebSocket 錯誤: {error}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket 關閉時的callback"""
        logger.info(f"Binance WebSocket 已關閉 (代碼: {close_status_code}, 訊息: {close_msg})")


# 測試用程式碼
if __name__ == "__main__":
    def test_callback(symbol: str, price: float):
        print(f"[測試] {symbol}: ${price:,.2f}")
    
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
