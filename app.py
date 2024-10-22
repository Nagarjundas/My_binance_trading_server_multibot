import os
from flask import Flask, request, jsonify
from binance.client import Client
from binance.enums import *
import telebot
import logging
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load bot configurations
with open('bot_config.json', 'r') as f:
    BOT_CONFIGS = json.load(f)

# Initialize Binance clients and Telegram bots for each configuration
binance_clients = {}
telegram_bots = {}

for bot_id, config in BOT_CONFIGS.items():
    binance_clients[bot_id] = Client(config['binance_api_key'], config['binance_secret_key'], testnet=True)
    telegram_bots[bot_id] = telebot.TeleBot(config['telegram_bot_token'])

def send_telegram_message(bot_id, message):
    try:
        telegram_bots[bot_id].send_message(BOT_CONFIGS[bot_id]['telegram_chat_id'], message)
        logger.info(f"Bot {bot_id}: Sent Telegram message: {message}")
    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to send Telegram message: {e}")

def execute_binance_order(bot_id, symbol, side, quantity):
    try:
        order = binance_clients[bot_id].create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        logger.info(f"Bot {bot_id}: Order executed: {order}")
        return order
    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to execute Binance order: {e}")
        return None

@app.route('/')
def home():
    return "Multi-Bot TradingView Webhook Server is running!"

@app.route('/webhook/<bot_id>', methods=['POST'])
def webhook(bot_id):
    if bot_id not in BOT_CONFIGS:
        return jsonify({'status': 'error', 'message': 'Invalid bot ID '}), 404

    if request.method == 'POST':
        data = request.json
        logger.info(f"Bot {bot_id}: Received webhook data: {data}")

        try:
            action = data['action']
            symbol = data['symbol']
            quantity = float(data['quantity'])
        except KeyError as e:
            return jsonify({'status': 'error', 'message': f'Missing required field: {str(e)}'}), 400
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid quantity format'}), 400

        if action not in ['BUY', 'SELL', 'TAKE_PROFIT', 'STOP_LOSS']:
            return jsonify({'status': 'error', 'message': 'Invalid action'}), 400

        # Execute order and send notification
        order = execute_binance_order(bot_id, symbol, SIDE_BUY if action == 'BUY' else SIDE_SELL, quantity)
        if order:
            emoji = {'BUY': '🟢', 'SELL': '🔴', 'TAKE_PROFIT': '💰', 'STOP_LOSS': '🛑'}[action]
            send_telegram_message(bot_id, f"{emoji} {action} order executed for {symbol}. Quantity: {quantity}")
            return jsonify({'status': 'success', 'message': 'Order processed'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Failed to execute order'}), 500

    return jsonify({'status': 'error', 'message': 'Invalid request method'}), 405

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))