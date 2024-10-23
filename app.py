import os
from flask import Flask, request, jsonify
from binance.client import Client
from binance.enums import *
import telebot
import logging
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

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

def get_account_balance(bot_id):
    """Get account balance for all assets with non-zero balance"""
    try:
        account = binance_clients[bot_id].get_account()
        balances = []
        for asset in account['balances']:
            # Convert strings to float
            free = float(asset['free'])
            locked = float(asset['locked'])
            # Only include assets with non-zero balance
            if free > 0 or locked > 0:
                balances.append({
                    'asset': asset['asset'],
                    'free': free,
                    'locked': locked,
                    'total': free + locked
                })
        logger.info(f"Bot {bot_id}: Retrieved account balances")
        return balances
    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to get account balance: {e}")
        return None

def get_recent_trades(bot_id, symbol, limit=10):
    """Get recent trades for a specific symbol"""
    try:
        trades = binance_clients[bot_id].get_my_trades(symbol=symbol, limit=limit)
        formatted_trades = []
        for trade in trades:
            formatted_trades.append({
                'symbol': trade['symbol'],
                'time': datetime.fromtimestamp(trade['time']/1000).strftime('%Y-%m-%d %H:%M:%S'),
                'side': 'BUY' if trade['isBuyer'] else 'SELL',
                'price': float(trade['price']),
                'quantity': float(trade['qty']),
                'commission': float(trade['commission']),
                'commission_asset': trade['commissionAsset'],
                'total': float(trade['price']) * float(trade['qty'])
            })
        logger.info(f"Bot {bot_id}: Retrieved recent trades for {symbol}")
        return formatted_trades
    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to get recent trades: {e}")
        return None

def get_open_orders(bot_id, symbol=None):
    """Get all open orders, optionally filtered by symbol"""
    try:
        if symbol:
            orders = binance_clients[bot_id].get_open_orders(symbol=symbol)
        else:
            orders = binance_clients[bot_id].get_open_orders()
        
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                'orderId': order['orderId'],
                'symbol': order['symbol'],
                'type': order['type'],
                'side': order['side'],
                'price': float(order['price']),
                'quantity': float(order['origQty']),
                'time': datetime.fromtimestamp(order['time']/1000).strftime('%Y-%m-%d %H:%M:%S')
            })
        logger.info(f"Bot {bot_id}: Retrieved open orders")
        return formatted_orders
    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to get open orders: {e}")
        return None

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

def format_balance_message(balances):
    """Format balance information for Telegram message"""
    message = "📊 *Account Balance*\n\n"
    for balance in balances:
        message += f"*{balance['asset']}*:\n"
        message += f"Free: {balance['free']:.8f}\n"
        message += f"Locked: {balance['locked']:.8f}\n"
        message += f"Total: {balance['total']:.8f}\n\n"
    return message

@app.route('/')
def home():
    return "Multi-Bot TradingView Webhook Server is running!"

@app.route('/webhook/<bot_id>', methods=['POST'])
def webhook(bot_id):
    if bot_id not in BOT_CONFIGS:
        return jsonify({'status': 'error', 'message': 'Invalid bot ID'}), 404

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

        # Execute order
        order = execute_binance_order(bot_id, symbol, SIDE_BUY if action == 'BUY' else SIDE_SELL, quantity)
        if order:
            # Get updated balance and recent trades
            balances = get_account_balance(bot_id)
            recent_trades = get_recent_trades(bot_id, symbol, limit=1)
            
            # Prepare notification message
            emoji = {'BUY': '🟢', 'SELL': '🔴', 'TAKE_PROFIT': '💰', 'STOP_LOSS': '🛑'}[action]
            message = f"{emoji} *{action} Order Executed*\n"
            message += f"Symbol: {symbol}\n"
            message += f"Quantity: {quantity}\n\n"
            
            if balances:
                message += format_balance_message(balances)
            
            if recent_trades:
                trade = recent_trades[0]
                message += f"\n*Latest Trade Details:*\n"
                message += f"Price: {trade['price']}\n"
                message += f"Total: {trade['total']}\n"
                message += f"Commission: {trade['commission']} {trade['commission_asset']}\n"
            
            send_telegram_message(bot_id, message)
            return jsonify({'status': 'success', 'message': 'Order processed'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Failed to execute order'}), 500

    return jsonify({'status': 'error', 'message': 'Invalid request method'}), 405

@app.route('/status/<bot_id>', methods=['GET'])
def get_status(bot_id):
    """Endpoint to get current account status"""
    if bot_id not in BOT_CONFIGS:
        return jsonify({'status': 'error', 'message': 'Invalid bot ID'}), 404

    balances = get_account_balance(bot_id)
    open_orders = get_open_orders(bot_id)

    return jsonify({
        'status': 'success',
        'balances': balances,
        'open_orders': open_orders
    }), 200

@app.route('/trades/<bot_id>/<symbol>', methods=['GET'])
def get_trades(bot_id, symbol):
    """Endpoint to get recent trades for a symbol"""
    if bot_id not in BOT_CONFIGS:
        return jsonify({'status': 'error', 'message': 'Invalid bot ID'}), 404

    limit = request.args.get('limit', default=10, type=int)
    trades = get_recent_trades(bot_id, symbol, limit=limit)

    if trades is None:
        return jsonify({'status': 'error', 'message': 'Failed to fetch trades'}), 500

    return jsonify({
        'status': 'success',
        'trades': trades
    }), 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))