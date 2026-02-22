#!/usr/bin/env python3
"""
FreqAI Training Trigger Script

Triggers training for every symbol/timeframe combination via the /api/v1/train endpoint.
Run with: python train_all.py
"""

import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = 'http://localhost:9000'

SYMBOLS = [
    'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD',
    'NZD/USD', 'USD/CAD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY',
    'EUR/AUD', 'XAU/USD',
    'BTC/USD', 'ETH/USD', 'BNB/USD', 'ADA/USD', 'SOL/USD',
    'XRP/USD', 'DOGE/USD', 'LINK/USD',
]

TIMEFRAMES = ['1h', '4h', '1d']


def trigger_training(symbol, timeframe):
    resp = requests.post(
        f'{BASE_URL}/api/v1/train',
        json={'symbol': symbol, 'timeframe': timeframe, 'limit': 5000},
        timeout=15
    )
    if resp.status_code == 200:
        data = resp.json()
        logger.info(f'  Training started: job_id={data.get("job_id")} model_id={data.get("model_id")}')
    else:
        logger.error(f'  FAILED: {resp.status_code} {resp.text[:100]}')


def main():
    total = len(SYMBOLS) * len(TIMEFRAMES)
    count = 0
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            count += 1
            logger.info(f'[{count}/{total}] Triggering: {symbol} {tf}')
            try:
                trigger_training(symbol, tf)
            except Exception as e:
                logger.error(f'  Exception: {e}')
            time.sleep(1)  # give background tasks breathing room
    logger.info('All training jobs triggered. Models train in background.')
    logger.info('Check /api/v1/models to see is_deployed status.')


if __name__ == '__main__':
    main()
