import os
from flask import Flask, request, jsonify
from binance.client import Client
from binance.enums import *
import telebot
import logging
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import re
from flask import render_template

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



def escape_markdown(text):
    """Escape characters that have special meaning in Markdown."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)


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
    
def get_symbol_balance_one_symbol(bot_id, symbol):
    """Get account balance for a specific asset (symbol)."""
    try:
        account = binance_clients[bot_id].get_account()
        for asset in account['balances']:
            if asset['asset'].upper() == symbol.upper():
                # Convert strings to float for free and locked balances
                free = float(asset['free'])
                locked = float(asset['locked'])
                total = free + locked
                # Return balance only if there is a non-zero balance
                if total > 0:
                    balance_info = {
                        'asset': asset['asset'],
                        'free': free,
                        'locked': locked,
                        'total': total
                    }
                    logger.info(f"Bot {bot_id}: Retrieved balance for {symbol}")
                    return balance_info
        # If no balance is found for the symbol
        logger.info(f"Bot {bot_id}: No balance found for {symbol}")
        return None
    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to get balance for {symbol}: {e}")
        return None


# Also update the send_telegram_message function for better error handling
def send_telegram_message(bot_id, message):
    try:
        if bot_id not in BOT_CONFIGS:
            raise ValueError(f"Invalid bot ID: {bot_id}")

        if not BOT_CONFIGS[bot_id].get('telegram_bot_token'):
            raise ValueError(f"Telegram bot token not configured for bot ID: {bot_id}")

        if not BOT_CONFIGS[bot_id].get('telegram_chat_id'):
            raise ValueError(f"Telegram chat ID not configured for bot ID: {bot_id}")

        # Add error handling for message content
        if not message or not isinstance(message, str):
            raise ValueError(f"Invalid message content: {message}")
        
        # Telegram message length check (4096 characters)
        max_length = 4096
        if len(message) > max_length:
            # Split message into chunks
            for i in range(0, len(message), max_length):
                telegram_bots[bot_id].send_message(
                    chat_id=BOT_CONFIGS[bot_id]['telegram_chat_id'],
                    text=message[i:i + max_length],
                    parse_mode='Markdown'
                )
        else:
            # Send the full message if it's within the limit
            telegram_bots[bot_id].send_message(
                chat_id=BOT_CONFIGS[bot_id]['telegram_chat_id'],
                text=message,
                parse_mode='Markdown'
            )
        logger.info(f"Bot {bot_id}: Telegram message sent successfully")

    except Exception as e:
        logger.error(f"Bot {bot_id}: Failed to send Telegram message: {str(e)}")
        raise



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
    """Format balance information for Telegram message, limiting message length"""
    message = "📊 *Account Balance*\n\n"
    for balance in balances:
        # Only include balances with a total > 0.01 to avoid small amounts
        if balance['total'] > 0.01:
            message += f"*{balance['asset']}*:\n"
            message += f"Free: {balance['free']:.8f}\n"
            message += f"Locked: {balance['locked']:.8f}\n"
            message += f"Total: {balance['total']:.8f}\n\n"
    return message


@app.route('/')
def home():
    """
    Serves the home page of the web application.
    """
    return render_template('index.html')


# ... (previous imports and configurations remain the same)

@app.route('/webhook/<bot_id>', methods=['POST'])
def webhook(bot_id):
    """
    Enhanced webhook endpoint with better error handling and request validation
    """
    logger.info(f"Received webhook request for bot_id: {bot_id}")
    
    # Validate bot_id
    if bot_id not in BOT_CONFIGS:
        logger.error(f"Invalid bot ID: {bot_id}")
        return jsonify({'status': 'error', 'message': 'Invalid bot ID'}), 404

    # Validate request content type
    if not request.is_json:
        logger.error(f"Invalid content type. Expected application/json, got {request.content_type}")
        return jsonify({
            'status': 'error',
            'message': 'Invalid content type. Please send JSON data with Content-Type: application/json'
        }), 400

    # Get and log raw request data
    raw_data = request.get_data()
    logger.info(f"Raw request data: {raw_data}")

    # Parse JSON data with error handling
    try:
        data = request.get_json()
        logger.info(f"Bot {bot_id}: Parsed webhook data: {data}")
        
        if not data:
            logger.error("Empty JSON data received")
            return jsonify({
                'status': 'error',
                'message': 'Empty JSON data received'
            }), 400

    except Exception as e:
        logger.error(f"JSON parsing error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Invalid JSON data: {str(e)}'
        }), 400

    # Validate required fields
    required_fields = ['action', 'symbol', 'quantity']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg
        }), 400

    try:
        action = data['action'].upper()
        symbol = data['symbol'].upper()
        quantity = float(data['quantity'])

        # Validate action
        valid_actions = ['BUY', 'SELL', 'TAKE_PROFIT', 'STOP_LOSS']
        if action not in valid_actions:
            logger.error(f"Invalid action: {action}")
            return jsonify({
                'status': 'error',
                'message': f'Invalid action. Must be one of: {", ".join(valid_actions)}'
            }), 400

        # Validate quantity
        if quantity <= 0:
            logger.error(f"Invalid quantity: {quantity}")
            return jsonify({
                'status': 'error',
                'message': 'Quantity must be greater than 0'
            }), 400

    except ValueError as e:
        logger.error(f"Value error in data validation: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Invalid numeric format: {str(e)}'
        }), 400

    # Execute order
    order = execute_binance_order(bot_id, symbol, SIDE_BUY if action == 'BUY' else SIDE_SELL, quantity)
    
    if not order:
        logger.error("Order execution failed")
        return jsonify({
            'status': 'error',
            'message': 'Failed to execute order'
        }), 500

    try:
        # Get updated balance for that symbol and recent trades
        balances = get_symbol_balance_one_symbol(bot_id,symbol)
        recent_trades = get_recent_trades(bot_id, symbol, limit=1)
        
        # Prepare notification message
        emoji = {'BUY': '🟢', 'SELL': '🔴', 'TAKE_PROFIT': '💰', 'STOP_LOSS': '🛑'}[action]
        message = (
            f"{emoji} *{action} Order Executed*\n"
            f"Symbol: {symbol}\n"
            f"Quantity: {quantity}\n\n"
        )
        
        if balances:
            message += "*Updated Balance:*\n"
            for balance in balances:
                if float(balance['total']) > 0:
                    message += (
                        f"{balance['asset']}:\n"
                        f"Free: {balance['free']:.8f}\n"
                        f"Locked: {balance['locked']:.8f}\n"
                        f"Total: {balance['total']:.8f}\n\n"
                    )
        
        if recent_trades:
            trade = recent_trades[0]
            message += (
                f"*Latest Trade Details:*\n"
                f"Price: {trade['price']}\n"
                f"Total: {trade['total']}\n"
                f"Commission: {trade['commission']} {trade['commission_asset']}\n"
            )

        # Send Telegram notification with error handling
        try:
            send_telegram_message(bot_id, message)
            logger.info("Telegram notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {str(e)}")
            # Continue execution even if Telegram notification fails
        
        return jsonify({
            'status': 'success',
            'message': 'Order processed',
            'order': order
        }), 200

    except Exception as e:
        logger.error(f"Error in post-order processing: {str(e)}")
        return jsonify({
            'status': 'success',
            'message': 'Order executed but failed to process additional information',
            'order': order
        }), 200



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

@app.route('/status/<bot_id>/<symbol>', methods=['GET'])
def get_single_status(bot_id,symbol):
    """Endpoint to get current account status for one symbol """
    if bot_id not in BOT_CONFIGS:
        return jsonify({'status': 'error', 'message': 'Invalid bot ID'}), 404

    balances = get_symbol_balance_one_symbol(bot_id,symbol)
    

    return jsonify({
        'status': 'success',
        'balances': balances,
        
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
