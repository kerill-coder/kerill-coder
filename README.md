# Trading Bot

## Requirements
- MetaTrader 5 (MT5)
- Python 3.8+

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/trading-bot.git
    cd trading-bot
    ```

2. Install required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Configure the `config.yaml` file with your MT5 credentials.

4. Run the Flask app:
    ```bash
    python app/bot.py
    ```

## Usage
- The bot will run with Flask on `http://localhost:5000`.
- Use the `/api/start` endpoint to start the bot (requires JWT authentication).

## Notes
- Ensure that MetaTrader 5 is running and connected to the appropriate account before starting the bot.
