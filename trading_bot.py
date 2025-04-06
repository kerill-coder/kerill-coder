# trading_bot.py
class TradingBot:
    def __init__(self):
        print("Trading Bot initialized")

    def start_trading(self):
        print("Trading started")

# main.py
from trading_bot import TradingBot

# Erstellen einer Instanz der Klasse TradingBot
bot = TradingBot()
bot.start_trading()

