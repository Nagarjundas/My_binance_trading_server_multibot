# Multi-Bot TradingView Webhook Server

This is a Flask-based server that handles webhooks from TradingView and executes trades on Binance using multiple bot configurations.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up your environment variables in the `.env` file.

3. Configure your bots in the `bot_config.json` file.

4. Run the server:
   ```
   python app.py
   ```

## Deployment

This application is ready to be deployed to a platform like Heroku. Make sure to set your environment variables in your deployment platform's settings.