my_project/
│
├── app.py             # Основной файл для запуска приложения (например, Flask)
├── requirements.txt   # Список зависимостей, если есть
├── config.yaml        # Конфигурационные файлы, если они есть
├── src/               # Исходный код
│   ├── __init__.py
│   ├── trading_bot.py
│   └── ...
└── README.md          # Документация, если она есть
python
import os
import logging
import requests
import joblib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token
from celery import Celery 
from binance.client import Client
from binance.exceptions import BinanceAPIException
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler
import redis
import yaml
import sqlite3
from datetime import datetime
import asyncio

# Load config
with open('config.yaml') as f:
    config = yaml.safe_load(f)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'default-secret-key')
jwt = JWTManager(app)

# Initialize Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Initialize Celery
celery = Celery('tasks', broker='redis://localhost:6379/0')

class TradingBot:
    def __init__(self):
        self.mt5_connected = False
        self.model = None
        self.scaler = MinMaxScaler()
        self.init_mt5()
        self.load_model()
        self.db_conn = sqlite3.connect(config['database']['path'])
        
    def init_mt5(self):
        try:
            if not mt5.initialize(
                login=config['mt5']['login'],
                password=config['mt5']['password'],
                server=config['mt5']['server']
            ):
                raise Exception("MT5 initialization failed")
            self.mt5_connected = True
            logger.info("MT5 initialized successfully")
        except Exception as e:
            logger.error(f"MT5 initialization error: {e}")
            
    def load_model(self):
        try:
            self.model = load_model('model.h5')
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Model loading error: {e}")
            
    async def get_market_data(self, symbol):
        try:
            rates = mt5.copy_rates_from_pos(
                symbol, 
                mt5.TIMEFRAME_M15, 
                0, 
                config['bars']
            )
            df = pd.DataFrame(rates)
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return None

    def calculate_position_size(self, symbol, risk_percent):
        try:
            account_info = mt5.account_info()
            balance = account_info.balance
            
            if config['risk']['position_sizing_method'] == 'fixed':
                return config['risk']['default_lot_size']
            
            # ATR-based position sizing
            atr = self.calculate_atr(symbol)
            risk_amount = balance * risk_percent
            pip_value = self.get_pip_value(symbol)
            position_size = risk_amount / (atr * pip_value)
            
            return round(position_size, 2)
        except Exception as e:
            logger.error(f"Position size calculation error: {e}")
            return config['risk']['default_lot_size']

    def calculate_atr(self, symbol):
        try:
            df = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, config['risk']['atr_period'])
            df = pd.DataFrame(df)
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    abs(df['high'] - df['close'].shift(1)),
                    abs(df['low'] - df['close'].shift(1))
                )
            )
            return df['tr'].mean()
        except Exception as e:
            logger.error(f"ATR calculation error: {e}")
            return None

    def get_pip_value(self, symbol):
        try:
            symbol_info = mt5.symbol_info(symbol)
            return symbol_info.trade_tick_value
        except Exception as e:
            logger.error(f"Pip value calculation error: {e}")
            return 0.0001

    @celery.task
    def process_signals():
        for symbol in config['symbols']:
            try:
                # Get market data
                df = self.get_market_data(symbol)
                if df is None:
                    continue
                
                # Prepare data for model
                X = self.prepare_data(df)
                
                # Get prediction
                prediction = self.model.predict(X)
                
                # Execute trade if signal is strong enough
                if abs(prediction[0]) > config['monitor']['alert_threshold']:
                    self.execute_trade(symbol, prediction[0])
                    
                # Store results
                self.store_trade_data(symbol, prediction[0])
                
            except Exception as e:
                logger.error(f"Signal processing error for {symbol}: {e}")

    def execute_trade(self, symbol, signal):
        try:
            if not self.check_risk_limits():
                logger.warning("Risk limits reached, skipping trade")
                return
                
            position_size = self.calculate_position_size(
                symbol, 
                config['risk']['max_risk_per_trade']
            )
            
            if signal > 0:
                order_type = mt5.ORDER_TYPE_BUY
            else:
                order_type = mt5.ORDER_TYPE_SELL
                
            price = mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
            
            sl = price - (config['risk']['stop_loss_pips'] * self.get_pip_value(symbol)) if order_type == mt5.ORDER_TYPE_BUY else price + (config['risk']['stop_loss_pips'] * self.get_pip_value(symbol))
            tp = price + (config['risk']['take_profit_pips'] * self.get_pip_value(symbol)) if order_type == mt5.ORDER_TYPE_BUY else price - (config['risk']['take_profit_pips'] * self.get_pip_value(symbol))
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": position_size,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "magic": 234000,
                "comment": "python script open",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order failed: {result.comment}")
            else:
                logger.info(f"Order executed: {symbol}, Signal: {signal}")
                
        except Exception as e:
            logger.error(f"Trade execution error: {e}")

    def check_risk_limits(self):
        try:
            # Check number of open positions
            positions = mt5.positions_total()
            if positions >= config['risk']['max_open_positions']:
                return False
                
            # Check daily risk
            daily_loss = self.calculate_daily_loss()
            if daily_loss >= config['risk']['max_daily_risk']:
                return False
                
            return True
        except Exception as e:
            logger.error(f"Risk check error: {e}")
            return False

    def calculate_daily_loss(self):
        try:
            today = datetime.now().date()
            history_deals = mt5.history_deals_get(
                datetime(today.year, today.month, today.day),
                datetime.now()
            )
            
            if history_deals is None:
                return 0
                
            total_loss = sum([deal.profit for deal in history_deals if deal.profit < 0])
            account_balance = mt5.account_info().balance
            
            return abs(total_loss) / account_balance
        except Exception as e:
            logger.error(f"Daily loss calculation error: {e}")
            return 0

    def store_trade_data(self, symbol, signal):
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('''
                INSERT INTO trades (symbol, signal, timestamp)
                VALUES (?, ?, ?)
            ''', (symbol, signal, datetime.now()))
            self.db_conn.commit()
        except Exception as e:
            logger.error(f"Database storage error: {e}")

    def __del__(self):
        if self.mt5_connected:
            mt5.shutdown()
        self.db_conn.close()

@app.route('/api/start', methods=['POST'])
@jwt_required()
def start_bot():
    try:
        bot = TradingBot()
        return jsonify({"status": "success", "message": "Bot started successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)


