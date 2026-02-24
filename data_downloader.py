#!/usr/bin/env python3
"""
FreqAI Data Downloader

Downloads 2+ years of historical market data from TwelveData API
and inserts into the FreqAI PostgreSQL database (TrainingData table).

Run with: python data_downloader.py
"""

import requests
import time
import logging
from datetime import datetime, timedelta
from database import SessionLocal, TrainingData
from config import TWELVE_DATA_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TWELVE_BASE = 'https://api.twelvedata.com'

SYMBOLS = [
    'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD',
    'NZD/USD', 'USD/CAD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY',
    'EUR/AUD', 'XAU/USD',
    'BTC/USD', 'ETH/USD', 'BNB/USD', 'ADA/USD', 'SOL/USD',
    'XRP/USD', 'DOGE/USD', 'LINK/USD',
]

TIMEFRAMES = {
    '1h': ('1h', 5000),    # TwelveData interval : max limit per request
    '4h': ('4h', 5000),
    '1d': ('1day', 5000),
}


def fetch_candles(symbol, td_interval, limit):
    """Fetch candles from TwelveData API."""
    url = f'{TWELVE_BASE}/time_series'
    params = {
        'symbol': symbol,
        'interval': td_interval,
        'outputsize': limit,
        'apikey': TWELVE_DATA_API_KEY,
        'format': 'json',
        'order': 'asc',
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get('status') == 'error':
        raise ValueError(data.get('message', 'API error'))
    return data.get('values', [])


def insert_candles(db, symbol, timeframe, candles):
    """Insert candles into TrainingData table, skip existing timestamps."""
    inserted = 0
    for c in candles:
        try:
            ts = datetime.strptime(c['datetime'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            ts = datetime.strptime(c['datetime'], '%Y-%m-%d')
        # Check if already exists
        exists = db.query(TrainingData).filter(
            TrainingData.symbol == symbol,
            TrainingData.timeframe == timeframe,
            TrainingData.timestamp == ts
        ).first()
        if exists:
            continue
        td = TrainingData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open=float(c['open']),
            high=float(c['high']),
            low=float(c['low']),
            close=float(c['close']),
            volume=float(c.get('volume', 0) or 0),
        )
        db.add(td)
        inserted += 1
    db.commit()
    return inserted


def main():
    db = SessionLocal()
    try:
        for symbol in SYMBOLS:
            for tf_key, (td_interval, limit) in TIMEFRAMES.items():
                try:
                    logger.info(f'Fetching {symbol} {tf_key}...')
                    candles = fetch_candles(symbol, td_interval, limit)
                    if not candles:
                        logger.warning(f'No candles for {symbol} {tf_key}')
                        continue
                    n = insert_candles(db, symbol, tf_key, candles)
                    count = db.query(TrainingData).filter(
                        TrainingData.symbol == symbol,
                        TrainingData.timeframe == tf_key
                    ).count()
                    logger.info(f'  {symbol} {tf_key}: +{n} new | total={count}')
                    time.sleep(0.5)  # respect rate limits
                except Exception as e:
                    logger.error(f'  ERROR {symbol} {tf_key}: {e}')
                    db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    main()
