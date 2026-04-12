#!/usr/bin/env python3
"""
TheArena - Full Historical Data Downloader
==========================================
- Downloads 15 years of data per symbol/timeframe
- Paginates TwelveData backwards in time (5000 candles per request)
- Checks existing DB coverage and only fetches missing ranges
- Fully resumable — safe to kill and restart anytime
- Respects 55 credits/min Grow plan limit with smart throttling
- Auto-backups PostgreSQL on completion

Usage:
    # Inside the container (recommended via screen):
    screen -S downloader
    docker exec -it thearena_freqai python historical_downloader.py

    # Or run directly on VPS if deps available:
    python historical_downloader.py --symbols EUR/USD BTC/USD
    python historical_downloader.py --timeframes 5m 15m 1h
    python historical_downloader.py --force   # re-download even if data exists
"""

import os
import sys
import time
import logging
import argparse
import subprocess
from datetime import datetime, timedelta
from typing import Optional

import requests
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# ── Bootstrap path so we can import project modules ──────────────────────────
sys.path.insert(0, '/app')
try:
    from database import TrainingData, Base
    from config import TWELVE_DATA_API_KEY, DATABASE_URL
except ImportError:
    # Fallback if running outside container
    from database import TrainingData, Base
    from config import TWELVE_DATA_API_KEY, DATABASE_URL

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/downloader.log', mode='a'),
    ]
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
TWELVE_BASE = 'https://api.twelvedata.com/time_series'

# How many years back to target per timeframe
TARGET_YEARS = {
    '5m':  15,
    '15m': 15,
    '30m': 15,
    '1h':  15,
    '4h':  15,
    '1d':  15,
    '1w':  15,
}

# TwelveData interval strings
TD_INTERVAL = {
    '5m':  '5min',
    '15m': '15min',
    '30m': '30min',
    '1h':  '1h',
    '4h':  '4h',
    '1d':  '1day',
    '1w':  '1week',
}

# Minutes per candle (used to estimate batch coverage)
MINUTES_PER_CANDLE = {
    '5m':  5,
    '15m': 15,
    '30m': 30,
    '1h':  60,
    '4h':  240,
    '1d':  1440,
    '1w':  10080,
}

BATCH_SIZE     = 5000   # max candles per TwelveData request
CREDITS_PER_MIN = 55    # Grow plan limit
# We use 1 credit per request. Leave headroom: target 45 req/min max.
# That means minimum 60/45 = 1.34s between requests.
# We use 1.5s to be safe, plus extra after every 40 requests.
REQUEST_DELAY   = 1.5   # seconds between every request
BURST_EVERY     = 40    # after this many requests, take a longer pause
BURST_PAUSE     = 15    # seconds for the longer pause

SYMBOLS = [
    'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD',
    'NZD/USD', 'USD/CAD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY',
    'EUR/AUD', 'XAU/USD',
    'BTC/USD', 'ETH/USD', 'BNB/USD', 'ADA/USD', 'SOL/USD',
    'XRP/USD', 'DOGE/USD', 'LINK/USD',
]

TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1d', '1w']

# ── DB setup ──────────────────────────────────────────────────────────────────
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

# ── Request counter for burst throttling ─────────────────────────────────────
_request_count = 0


def _sleep_with_log(seconds: float, reason: str = ''):
    if seconds > 3:
        logger.info(f'  ⏳ Pausing {seconds:.0f}s {reason}')
    time.sleep(seconds)


def fetch_batch(
    symbol: str,
    tf: str,
    end_date: datetime,
    outputsize: int = BATCH_SIZE,
) -> list:
    """
    Fetch up to `outputsize` candles ending at `end_date`.
    Returns list of dicts with datetime/open/high/low/close/volume.
    Raises on API error.
    """
    global _request_count

    params = {
        'symbol':     symbol,
        'interval':   TD_INTERVAL[tf],
        'outputsize': outputsize,
        'end_date':   end_date.strftime('%Y-%m-%d %H:%M:%S'),
        'apikey':     TWELVE_DATA_API_KEY,
        'format':     'json',
        'order':      'asc',
    }

    _request_count += 1

    # Burst throttle
    if _request_count % BURST_EVERY == 0:
        _sleep_with_log(BURST_PAUSE, f'(burst pause every {BURST_EVERY} requests)')

    try:
        resp = requests.get(TWELVE_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        logger.warning('  Request timed out — waiting 30s before retry')
        time.sleep(30)
        resp = requests.get(TWELVE_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    if data.get('status') == 'error':
        msg = data.get('message', 'unknown API error')
        # Rate limit hit
        if 'limit' in msg.lower() or '429' in msg:
            logger.warning(f'  Rate limit hit — sleeping 60s')
            time.sleep(60)
            raise RuntimeError(f'Rate limited: {msg}')
        raise ValueError(f'API error: {msg}')

    values = data.get('values', [])
    return values


def get_existing_range(db, symbol: str, tf: str):
    """Return (min_ts, max_ts, count) for existing data, or (None, None, 0)."""
    row = db.query(
        func.min(TrainingData.timestamp),
        func.max(TrainingData.timestamp),
        func.count(TrainingData.id),
    ).filter(
        TrainingData.symbol == symbol,
        TrainingData.timeframe == tf,
    ).first()
    if row and row[2] > 0:
        return row[0], row[1], row[2]
    return None, None, 0


def parse_ts(dt_str: str) -> datetime:
    """Parse TwelveData datetime string."""
    try:
        return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return datetime.strptime(dt_str, '%Y-%m-%d')


def insert_batch(db, symbol: str, tf: str, candles: list) -> int:
    """
    Bulk-insert candles, skipping duplicates.
    Returns number of new rows inserted.
    """
    if not candles:
        return 0

    # Collect timestamps already in DB for this batch range
    batch_start = parse_ts(candles[0]['datetime'])
    batch_end   = parse_ts(candles[-1]['datetime'])
    existing_ts = set(
        r[0] for r in db.query(TrainingData.timestamp).filter(
            TrainingData.symbol    == symbol,
            TrainingData.timeframe == tf,
            TrainingData.timestamp >= batch_start,
            TrainingData.timestamp <= batch_end,
        ).all()
    )

    new_rows = []
    for c in candles:
        ts = parse_ts(c['datetime'])
        if ts in existing_ts:
            continue
        new_rows.append(TrainingData(
            symbol    = symbol,
            timeframe = tf,
            timestamp = ts,
            open      = float(c['open']),
            high      = float(c['high']),
            low       = float(c['low']),
            close     = float(c['close']),
            volume    = float(c.get('volume') or 0),
        ))

    if new_rows:
        db.bulk_save_objects(new_rows)
        db.commit()

    return len(new_rows)


def download_symbol_timeframe(
    symbol: str,
    tf: str,
    force: bool = False,
) -> dict:
    """
    Download full history for one symbol/timeframe.
    Paginates backwards from today until target start date.
    Skips ranges already in DB unless force=True.
    Returns stats dict.
    """
    db = Session()
    stats = {'inserted': 0, 'batches': 0, 'skipped_batches': 0, 'errors': 0}

    try:
        target_years  = TARGET_YEARS.get(tf, 15)
        target_start  = datetime.utcnow() - timedelta(days=target_years * 365)
        candle_minutes = MINUTES_PER_CANDLE[tf]

        # Check existing coverage
        existing_min, existing_max, existing_count = get_existing_range(db, symbol, tf)

        if existing_count > 0 and not force:
            logger.info(
                f'  Existing: {existing_count:,} candles '
                f'({str(existing_min)[:10]} → {str(existing_max)[:10]})'
            )
            # Only need to fetch data BEFORE existing minimum
            fetch_end = existing_min - timedelta(minutes=candle_minutes)
            if fetch_end <= target_start:
                logger.info(f'  ✅ Already have full {target_years}yr history — skipping')
                return stats
        else:
            fetch_end = datetime.utcnow()

        logger.info(
            f'  Fetching from {str(target_start)[:10]} → {str(fetch_end)[:10]} '
            f'({target_years}yr target)'
        )

        batch_num   = 0
        current_end = fetch_end

        while current_end > target_start:
            batch_num += 1
            try:
                candles = fetch_batch(symbol, tf, end_date=current_end)
            except (ValueError, RuntimeError) as e:
                logger.error(f'  ❌ Batch {batch_num} error: {e}')
                stats['errors'] += 1
                if stats['errors'] >= 5:
                    logger.error(f'  Too many errors for {symbol} {tf} — aborting this pair')
                    break
                time.sleep(10)
                continue

            if not candles:
                logger.info(f'  No more data returned — reached exchange history limit')
                break

            inserted = insert_batch(db, symbol, tf, candles)
            stats['inserted']    += inserted
            stats['batches']     += 1
            stats['skipped_batches'] += (1 if inserted == 0 else 0)

            oldest_in_batch = parse_ts(candles[0]['datetime'])
            newest_in_batch = parse_ts(candles[-1]['datetime'])

            logger.info(
                f'  Batch {batch_num:3d}: {len(candles):5,} candles '
                f'({str(oldest_in_batch)[:10]} → {str(newest_in_batch)[:10]}) '
                f'+{inserted:,} new'
            )

            # Move end pointer back to just before oldest candle in this batch
            current_end = oldest_in_batch - timedelta(minutes=candle_minutes)

            # Check if we've gone far enough back
            if oldest_in_batch <= target_start:
                logger.info(f'  Reached target start date {str(target_start)[:10]}')
                break

            # Per-request delay
            _sleep_with_log(REQUEST_DELAY)

        # Final count
        _, _, final_count = get_existing_range(db, symbol, tf)
        logger.info(
            f'  ✅ Done — total in DB: {final_count:,} candles | '
            f'inserted this run: {stats["inserted"]:,}'
        )

    except Exception as e:
        logger.error(f'  ❌ Unexpected error: {e}', exc_info=True)
        db.rollback()
    finally:
        db.close()

    return stats


def backup_database():
    """Dump PostgreSQL to a timestamped backup file."""
    ts        = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backup_dir = '/opt/backups/thearena'
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = f'{backup_dir}/freqai_historical_{ts}.sql.gz'

    logger.info(f'📦 Backing up database → {backup_file}')

    # Extract DB connection info from DATABASE_URL
    # Expected format: postgresql://user:pass@host:port/dbname
    db_url = DATABASE_URL
    cmd = (
        f'docker exec thearena_freqai_postgres pg_dumpall -U postgres '
        f'| gzip > {backup_file}'
    )

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            size = os.path.getsize(backup_file)
            logger.info(f'  ✅ Backup complete: {backup_file} ({size / 1024 / 1024:.1f} MB)')
        else:
            logger.error(f'  ❌ Backup failed: {result.stderr}')
            # Try alternative: pg_dump inside the postgres container
            cmd2 = (
                f'docker exec thearena_freqai_postgres pg_dump -U postgres freqai '
                f'> {backup_file.replace(".gz", "")} 2>&1'
            )
            subprocess.run(cmd2, shell=True)
            logger.info(f'  Fallback backup attempted: {backup_file.replace(".gz", "")}')
    except Exception as e:
        logger.error(f'  ❌ Backup exception: {e}')


def print_summary(symbol: str, tf: str, stats: dict):
    return (
        f'{symbol:15} {tf:5} '
        f'batches={stats["batches"]:3} '
        f'inserted={stats["inserted"]:7,} '
        f'errors={stats["errors"]}'
    )


def main():
    parser = argparse.ArgumentParser(description='TheArena Historical Data Downloader')
    parser.add_argument('--symbols',    nargs='+', default=None,
                        help='Only these symbols e.g. EUR/USD BTC/USD')
    parser.add_argument('--timeframes', nargs='+', default=None,
                        help='Only these timeframes e.g. 5m 15m 1h')
    parser.add_argument('--force',      action='store_true',
                        help='Re-download even if data already exists')
    parser.add_argument('--no-backup',  action='store_true',
                        help='Skip database backup on completion')
    args = parser.parse_args()

    symbols    = args.symbols    or SYMBOLS
    timeframes = args.timeframes or TIMEFRAMES
    # Keep canonical order
    timeframes = [tf for tf in TIMEFRAMES if tf in timeframes]

    total_tasks = len(symbols) * len(timeframes)
    logger.info('=' * 65)
    logger.info('TheArena Historical Data Downloader')
    logger.info(f'Symbols     : {len(symbols)}')
    logger.info(f'Timeframes  : {timeframes}')
    logger.info(f'Target      : 15 years per pair')
    logger.info(f'Rate limit  : {CREDITS_PER_MIN} credits/min (Grow plan)')
    logger.info(f'Request gap : {REQUEST_DELAY}s + {BURST_PAUSE}s every {BURST_EVERY} requests')
    logger.info(f'Total tasks : {total_tasks}')
    logger.info(f'Force mode  : {args.force}')
    logger.info('=' * 65)

    all_stats = []
    start_time = datetime.utcnow()

    task_num = 0
    for symbol in symbols:
        for tf in timeframes:
            task_num += 1
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if task_num > 1:
                avg = elapsed / (task_num - 1)
                eta_sec = avg * (total_tasks - task_num + 1)
                eta_str = str(timedelta(seconds=int(eta_sec)))
            else:
                eta_str = '??'

            logger.info('')
            logger.info(
                f'[{task_num}/{total_tasks}]  {symbol}  {tf}  '
                f'(elapsed={str(timedelta(seconds=int(elapsed)))}  ETA={eta_str})'
            )

            stats = download_symbol_timeframe(symbol, tf, force=args.force)
            stats['symbol'] = symbol
            stats['tf']     = tf
            all_stats.append(stats)

    # ── Final summary ─────────────────────────────────────────────────────
    total_elapsed = datetime.utcnow() - start_time
    total_inserted = sum(s['inserted'] for s in all_stats)
    total_errors   = sum(s['errors']   for s in all_stats)

    logger.info('')
    logger.info('=' * 65)
    logger.info(f'Download complete in {total_elapsed}')
    logger.info(f'Total candles inserted : {total_inserted:,}')
    logger.info(f'Total errors           : {total_errors}')
    logger.info('')

    if total_errors > 0:
        logger.info('Pairs with errors:')
        for s in all_stats:
            if s['errors'] > 0:
                logger.info(f'  {s["symbol"]} {s["tf"]} — {s["errors"]} errors')

    logger.info('')
    logger.info('Final DB coverage:')
    db = Session()
    try:
        results = db.query(
            TrainingData.symbol,
            TrainingData.timeframe,
            func.count(TrainingData.id),
            func.min(TrainingData.timestamp),
            func.max(TrainingData.timestamp),
        ).group_by(
            TrainingData.symbol,
            TrainingData.timeframe,
        ).order_by(
            TrainingData.symbol,
            TrainingData.timeframe,
        ).all()

        for r in results:
            years = (r[4] - r[3]).days / 365 if r[3] and r[4] else 0
            logger.info(
                f'  {r[0]:15} {r[1]:5} '
                f'count={r[2]:7,}  '
                f'{str(r[3])[:10]} → {str(r[4])[:10]}  '
                f'({years:.1f} yrs)'
            )
    finally:
        db.close()

    logger.info('=' * 65)

    # ── Backup ────────────────────────────────────────────────────────────
    if not args.no_backup:
        backup_database()

    logger.info('')
    logger.info('✅ All done. You can now retrain models with full historical data.')
    logger.info('   Run: python train_all.py --force')


if __name__ == '__main__':
    main()
