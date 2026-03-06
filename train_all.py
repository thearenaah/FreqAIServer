#!/usr/bin/env python3
"""
FreqAI Training Script - TheArena v2
=====================================
Key change from v1:
  - Trains in DEPENDENCY ORDER: higher timeframes first.
    This ensures HTF features are available when lower TF models train.
  - Configurable concurrency (default: sequential to avoid DB pool exhaustion)
  - Progress tracking with ETA
  - Skips already-trained models unless --force flag is used

Usage:
    python train_all.py              # train all missing/outdated models
    python train_all.py --force      # retrain everything
    python train_all.py --tf 1h 4h   # only specific timeframes
    python train_all.py --sym BTC/USD EUR/USD  # only specific symbols
"""

import requests
import time
import logging
import argparse
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

BASE_URL = 'http://localhost:9000'
TIMEOUT  = 900   # max seconds to wait per job (15 min for large datasets)

SYMBOLS = [
    # Forex majors
    'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD',
    'NZD/USD', 'USD/CAD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY',
    'EUR/AUD', 'XAU/USD',
    # Crypto
    'BTC/USD', 'ETH/USD', 'BNB/USD', 'ADA/USD', 'SOL/USD',
    'XRP/USD', 'DOGE/USD', 'LINK/USD',
]

# Train from HIGHEST timeframe → LOWEST so HTF features are ready
# when lower-TF models try to load them at training time.
TIMEFRAMES_ORDERED = ['1w', '1d', '4h', '1h', '30m', '15m', '5m']


# ─────────────────────────────────────────────
#  API helpers
# ─────────────────────────────────────────────

def get_deployed_models():
    """Return set of (symbol, timeframe) tuples that are already deployed."""
    try:
        resp = requests.get(f'{BASE_URL}/api/v1/models', timeout=10)
        if resp.status_code == 200:
            return {
                (m['symbol'], m['timeframe'])
                for m in resp.json()
                if m.get('is_deployed')
            }
    except Exception as e:
        logger.warning(f'Could not fetch deployed models: {e}')
    return set()


def trigger_training(symbol: str, timeframe: str):
    resp = requests.post(
        f'{BASE_URL}/api/v1/train',
        json={'symbol': symbol, 'timeframe': timeframe, 'limit': 5000},
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info(f'  Started → job_id={data.get("job_id")} model_id={data.get("model_id")}')
    return data.get('job_id'), data.get('model_id')


def wait_for_job(job_id, symbol: str, timeframe: str) -> bool:
    """Poll until job completes or times out. Returns True on success."""
    start = time.time()
    dot_count = 0
    while time.time() - start < TIMEOUT:
        try:
            resp = requests.get(f'{BASE_URL}/api/v1/jobs/{job_id}', timeout=60)
            if resp.status_code == 200:
                data   = resp.json()
                status = data.get('status', 'unknown')
                if status == 'completed':
                    elapsed = time.time() - start
                    logger.info(f'  ✓ {symbol} {timeframe}  ({elapsed:.0f}s)')
                    return True
                elif status == 'failed':
                    logger.error(f'  ✗ {symbol} {timeframe}: {data.get("error_message", "unknown")}')
                    return False
                else:
                    dot_count += 1
                    if dot_count % 6 == 0:
                        elapsed = time.time() - start
                        logger.info(f'  … {symbol} {timeframe}  status={status}  ({elapsed:.0f}s)')
            elif resp.status_code == 404:
                # No job endpoint — just wait
                time.sleep(30)
                return True
        except Exception as e:
            logger.warning(f'  Poll error: {e}')
            time.sleep(15)  # back off on error
        time.sleep(15)  # slower polling to reduce DB load
    logger.error(f'  ✗ {symbol} {timeframe}: timed out after {TIMEOUT}s')
    return False


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Train FreqAI models')
    parser.add_argument('--force', action='store_true',
                        help='Retrain even if model already deployed')
    parser.add_argument('--tf', nargs='+', default=None,
                        help='Only train these timeframes (e.g. --tf 1h 4h)')
    parser.add_argument('--sym', nargs='+', default=None,
                        help='Only train these symbols (e.g. --sym BTC/USD EUR/USD)')
    args = parser.parse_args()

    symbols    = args.sym    or SYMBOLS
    timeframes = args.tf     or TIMEFRAMES_ORDERED
    # Keep dependency order even if user specified subset
    timeframes = [tf for tf in TIMEFRAMES_ORDERED if tf in timeframes]

    already_deployed = set() if args.force else get_deployed_models()
    logger.info(f'Already deployed: {len(already_deployed)} models')

    tasks = [
        (sym, tf)
        for tf  in timeframes
        for sym in symbols
        if (sym, tf) not in already_deployed
    ]

    total   = len(tasks)
    success = 0
    failed  = []
    start_t = datetime.now()

    logger.info(f'Training {total} models in dependency order (HTF → LTF)…')
    logger.info(f'Order: {" → ".join(timeframes)}\n')

    for idx, (symbol, tf) in enumerate(tasks, 1):
        elapsed_total = (datetime.now() - start_t).total_seconds()
        if idx > 1:
            avg_per_job = elapsed_total / (idx - 1)
            eta = timedelta(seconds=int(avg_per_job * (total - idx + 1)))
        else:
            eta = timedelta(seconds=0)

        logger.info(f'[{idx}/{total}]  {symbol}  {tf}  (ETA: {eta})')

        try:
            job_id, model_id = trigger_training(symbol, tf)
            if job_id:
                ok = wait_for_job(job_id, symbol, tf)
            else:
                time.sleep(30)
                ok = True

            if ok:
                success += 1
            else:
                failed.append(f'{symbol} {tf}')
        except Exception as e:
            logger.error(f'  Exception: {e}')
            failed.append(f'{symbol} {tf}')
            time.sleep(2)

    # ── Summary ───────────────────────────────────────────────────────
    total_time = datetime.now() - start_t
    print()
    logger.info('═' * 60)
    logger.info(f'Training complete in {total_time}')
    logger.info(f'  Success : {success}/{total}')
    logger.info(f'  Skipped : {len(already_deployed)} (already deployed)')
    if failed:
        logger.warning(f'  Failed  : {len(failed)}')
        for f in failed:
            logger.warning(f'    - {f}')
    logger.info('═' * 60)


if __name__ == '__main__':
    main()
