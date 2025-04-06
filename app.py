from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token
from modules.mt5_interface import MT5Interface
from modules.strategy import TradingStrategy
from modules.risk_management import RiskManager
import sqlite3
import yaml
import os

# Load config
with open('config.yaml') as f:
    config = yaml.safe_load(f)

# Flask setup
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'super-secret-key')
jwt = JWTManager(app)

# Init services
mt5 = MT5Interface(config)
strategy = TradingStrategy()
risk = RiskManager(config)

@app.route('/api/start', methods=['POST'])
@jwt_required()
def start():
    symbol = request.json.get('symbol')
    signal = strategy.generate_signal(symbol)
    if signal:
        risk.execute_trade(symbol, signal)
    return jsonify({'message': 'Trade processed'})

if __name__ == '__main__':
    app.run(debug=True)
