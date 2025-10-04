import eventlet # 使用 async_mode eventlet
eventlet.monkey_patch() # 用這個才可以讓async_mode = 'eventlet' 正常運作 否則使用 mode 'threading'

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from datetime import datetime
from typing import Dict, Set
import logging

from binance_websocket import BinanceWebSocket
from bybit_websocket import BybitWebSocket
from coinbase_websocket import CoinbaseWebSocket
from okx_websocket import OkxWebSocket
from bitget_websocket import BitgetWebSocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 支援的加密貨幣列表
SUPPORTED_COINS = {
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'BNB': 'Binance Coin',
    'SOL': 'Solana',
    'XRP': 'Ripple',
    'ADA': 'Cardano',
    'DOGE': 'Dogecoin',
    'MATIC': 'Polygon',
}

# Global variables
price_cache: Dict[str, Dict[str, float]] = {}  # {coin: {exchange: price}}
user_watching: Dict[str, str] = {}  # {session_id: coin_symbol} - 追蹤每個使用者正在查看的幣種
active_subscriptions: Dict[str, int] = {}  # {coin_symbol: count} - 追蹤每個幣種的訂閱數量
ws_pool = []

def on_price_update(symbol: str, price: float, exchange: str): # TODO: timestamp
    """
    通用價格更新處理函數
    """
    # 更新價格快取
    logger.debug(f"價格更新: {exchange} {symbol} = ${price:,.2f}")
    if symbol not in price_cache:
        price_cache[symbol] = {}
    price_cache[symbol][exchange] = price
    logger.debug(f"價格更新快取: {exchange} {symbol} = ${price:,.2f}")
    # 只發送給正在查看這個幣種的使用者
    socketio.emit('price_update', {
        'symbol': symbol,
        'exchange': exchange,
        'price': price,
        'timestamp': datetime.now().isoformat()
    }, room=f'coin_{symbol}')
    
    logger.debug(f"價格更新已發送到 room coin_{symbol}: {exchange} {symbol} = ${price:,.2f}")


def update_subscriptions(symbol: str, increment: bool = True):
    """
    更新幣種訂閱計數
    """
    if increment:
        active_subscriptions[symbol] = active_subscriptions.get(symbol, 0) + 1
        logger.info(f"{symbol} 訂閱數增加到 {active_subscriptions[symbol]}")
        
        # 如果是第一次訂閱，通知 WebSocket 開始接收該幣種資料
        if active_subscriptions[symbol] == 1:
            for ws in ws_pool:
                ws.subscribe(symbol)
            logger.info(f"開始訂閱 Binance {symbol} 資料")
    else:
        if symbol in active_subscriptions:
            active_subscriptions[symbol] = max(0, active_subscriptions[symbol] - 1)
            logger.info(f"{symbol} 訂閱數減少到 {active_subscriptions[symbol]}")
            
            # 如果沒有人訂閱了，取消 WebSocket 訂閱
            if active_subscriptions[symbol] == 0:
                for ws in ws_pool:
                    ws.unsubscribe(symbol) 
                logger.info(f"停止訂閱 Binance {symbol} 資料")


@app.route('/')
def index():
    return render_template('index.html', coins=SUPPORTED_COINS)

@app.route('/coin/<symbol>')
def coin_page(symbol):
    """顯示特定加密貨幣的頁面"""
    symbol = symbol.upper()
    
    if symbol not in SUPPORTED_COINS:
        return "不支援的加密貨幣", 404
    
    return render_template('coin.html', 
                         coin_symbol=symbol, 
                         coin_name=SUPPORTED_COINS[symbol])

@socketio.on('connect')
def handle_connect():
    """處理客戶端連接"""
    logger.info(f"客戶端已連接: {request.sid}")
    emit('connection_response', {'status': 'connected', 'sid': request.sid})


@socketio.on('disconnect')
def handle_disconnect():
    """處理客戶端斷線"""
    logger.info(f"客戶端已斷線: {request.sid}")
    
    # 如果使用者正在查看某個幣種，取消訂閱
    if request.sid in user_watching:
        symbol = user_watching[request.sid]
        leave_room(f'coin_{symbol}')
        update_subscriptions(symbol, increment=False)
        del user_watching[request.sid]
        logger.info(f"使用者 {request.sid} 離開，取消 {symbol} 訂閱")


@socketio.on('watch_coin')
def handle_watch_coin(data):
    """
    處理使用者開始查看某個幣種
    """
    symbol = data.get('symbol', '').upper()
    
    if symbol not in SUPPORTED_COINS:
        emit('error', {'message': '不支援的幣種'})
        return
    
    # 如果使用者之前在看其他幣種，先取消舊的訂閱
    if request.sid in user_watching:
        old_symbol = user_watching[request.sid]
        if old_symbol != symbol:
            leave_room(f'coin_{old_symbol}')
            update_subscriptions(old_symbol, increment=False)
            logger.info(f"使用者 {request.sid} 從 {old_symbol} 切換到 {symbol}")
    
    # 記錄使用者正在查看這個幣種
    user_watching[request.sid] = symbol
    join_room(f'coin_{symbol}')
    update_subscriptions(symbol, increment=True)
    
    logger.info(f"使用者 {request.sid} 開始查看 {symbol}")
    
    # 發送當前快取的價格（如果有）
    if symbol in price_cache :
        for exchange, price in price_cache[symbol].items():
            emit('price_update', {
                'symbol': symbol,
                'exchange': exchange,
                'price': price,
                'timestamp': datetime.now().isoformat()
            }, room=f'coin_{symbol}')
            logger.debug(f"發送快取價格到 room coin_{symbol}: {exchange} {symbol} = ${price:,.2f}")
    emit('watch_response', {'status': 'success', 'symbol': symbol})


@socketio.on('unwatch_coin')
def handle_unwatch_coin(data):
    """
    處理使用者停止查看某個幣種
    """
    symbol = data.get('symbol', '').upper()
    
    if request.sid in user_watching and user_watching[request.sid] == symbol:
        leave_room(f'coin_{symbol}')
        update_subscriptions(symbol, increment=False)
        del user_watching[request.sid]
        logger.info(f"使用者 {request.sid} 停止查看 {symbol}")
        
        emit('unwatch_response', {'status': 'success', 'symbol': symbol})

if __name__ == '__main__':
    # 初始化並啟動 Binance WebSocket
    logger.info("正在啟動 WebSocket...")
    ws_pool.append(BinanceWebSocket(callback=on_price_update))
    ws_pool.append(BybitWebSocket(callback=on_price_update))
    ws_pool.append(CoinbaseWebSocket(callback=on_price_update))
    ws_pool.append(OkxWebSocket(callback=on_price_update))
    ws_pool.append(BitgetWebSocket(callback=on_price_update))
    for ws in ws_pool:
        ws.start()

    try:
        # 啟動 Flask-SocketIO 伺服器
        logger.info("正在啟動 Flask 伺服器...")
        socketio.run(app, debug=True, port=5000, use_reloader=False)
    finally:
        # 關閉 WebSocket 連接
        for ws in ws_pool:
            logger.info(f"正在關閉 {ws.__class__.__name__} WebSocket...")
            ws.stop()
