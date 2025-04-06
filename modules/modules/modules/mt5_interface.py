import MetaTrader5 as mt5
import logging

class MT5Interface:
    def __init__(self, config):
        self.config = config
        if not mt5.initialize(**config['mt5']):
            logging.error("Не удалось инициализировать MT5: %s", mt5.last_error())
            raise RuntimeError("Не удалось инициализировать MT5")
        logging.info("MT5 подключен")

    def shutdown(self):
        mt5.shutdown()
        logging.info("MT5 отключен")

# Пример конфигурации
config = {
    'mt5': {
        'login': 12345678,
        'password': 'password',
        'server': 'broker-server'
    }
}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        mt5_interface = MT5Interface(config)
        # Дополнительные операции с MT5
    except RuntimeError as e:
        logging.error("Произошла ошибка: %s", e)
    finally:
        mt5_interface.shutdown()