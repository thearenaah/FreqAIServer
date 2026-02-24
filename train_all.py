#!/usr/bin/env python3
"""
FreqAI Training Trigger Script
Triggers training for every symbol/timeframe combination via the /api/v1/train endpoint.
Waits for each job to complete before starting the next to avoid DB pool exhaustion.
Run with: python train_all.py
"""
import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = 'http://localhost:9000'
TIMEOUT = 300  # max seconds to wait per training job

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
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info(f'  Training started: job_id={data.get("job_id")} model_id={data.get("model_id")}')
    return data.get('job_id'), data.get('model_id')


def wait_for_job(job_id, symbol, timeframe):
    """Poll /api/v1/jobs/{job_id} until complete or timeout."""
    start = time.time()
    while time.time() - start < TIMEOUT:
        try:
            resp = requests.get(f'{BASE_URL}/api/v1/jobs/{job_id}', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get('status', 'unknown')
                if status == 'completed':
                    logger.info(f'  ✓ {symbol} {timeframe} completed')
                    return True
                elif status == 'failed':
                    logger.error(f'  ✗ {symbol} {timeframe} failed: {data.get("error_message")}')
                    return False
                else:
                    logger.info(f'  ... {symbol} {timeframe} status={status} progress={data.get("progress", 0)}%')
            elif resp.status_code == 404:
                # No jobs endpoint - just wait a fixed time
                time.sleep(30)
                return True
        except Exception as e:
            logger.warning(f'  Poll error: {e}')
        time.sleep(5)
    logger.error(f'  ✗ {symbol} {timeframe} timed out after {TIMEOUT}s')
    return False


def main():
    total = len(SYMBOLS) * len(TIMEFRAMES)
    count = 0
    failed = []

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            count += 1
            logger.info(f'[{count}/{total}] Triggering: {symbol} {tf}')
            try:
                job_id, model_id = trigger_training(symbol, tf)
                if job_id:
                    wait_for_job(job_id, symbol, tf)
                else:
                    # No job_id returned, wait a flat interval
                    time.sleep(30)
            except Exception as e:
                logger.error(f'  Exception: {e}')
                failed.append(f'{symbol} {tf}')
                time.sleep(2)

    logger.info(f'\nDone. {total - len(failed)}/{total} succeeded.')
    if failed:
        logger.warning(f'Failed: {failed}')


if __name__ == '__main__':
    main()
