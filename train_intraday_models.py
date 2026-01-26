#!/usr/bin/env python3
"""
Train intraday timeframes (1m, 5m, 15m, 30m)
These provide rapid signals for high-frequency traders
Uses same aggressive label strategy (0.25% threshold + 1.05x ratio)
"""

import logging
import requests
import time
from market_data import MarketDataFetcher
from database import SessionLocal, TrainingData

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Target symbols
ASSETS = {
    'forex_majors': [
        'EUR/USD', 'GBP/USD', 'USD/JPY', 'XAU/USD', 'AUD/USD',
        'USD/CAD', 'USD/CHF', 'GBP/JPY', 'EUR/AUD', 'GBP/AUD',
    ],
    'major_crypto': [
        'BTC/USD', 'ETH/USD', 'LTC/USD',
    ]
}

all_symbols = ASSETS['forex_majors'] + ASSETS['major_crypto']
intraday_timeframes = ['1m', '5m', '15m', '30m']

FREQAI_URL = 'http://localhost:9000'
fetcher = MarketDataFetcher()
db = SessionLocal()

def import_intraday_data():
    """Import data for intraday timeframes"""
    
    print("\n" + "="*80)
    print("📥 IMPORTING INTRADAY DATA")
    print("="*80)
    print(f"Timeframes: {', '.join(intraday_timeframes)}")
    print(f"Symbols: {len(all_symbols)}\n")
    
    # Candle counts for each timeframe
    candle_counts = {
        '1m': 1000,   # ~16 hours of data
        '5m': 500,    # ~3.5 days
        '15m': 500,   # ~10 days
        '30m': 500,   # ~20 days
    }
    
    import_stats = {'success': 0, 'failed': 0}
    
    for symbol in all_symbols:
        for timeframe in intraday_timeframes:
            try:
                candle_count = candle_counts[timeframe]
                data = fetcher.fetch_ohlcv(symbol, timeframe, candle_count)
                
                if data:
                    # Clear old data
                    deleted = db.query(TrainingData).filter(
                        TrainingData.symbol == symbol,
                        TrainingData.timeframe == timeframe
                    ).delete()
                    
                    # Insert new data
                    for candle in data:
                        td = TrainingData(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=candle['timestamp'],
                            open=float(candle['open']),
                            high=float(candle['high']),
                            low=float(candle['low']),
                            close=float(candle['close']),
                            volume=float(candle['volume']) if candle['volume'] else 0
                        )
                        db.add(td)
                    
                    db.commit()
                    print(f"  ✅ {symbol:12} {timeframe:3}  {len(data):4} candles")
                    import_stats['success'] += 1
                else:
                    print(f"  ⚠️  {symbol:12} {timeframe:3}  No data")
                    import_stats['failed'] += 1
                    
            except Exception as e:
                logger.error(f"  ❌ {symbol} {timeframe}: {str(e)[:50]}")
                db.rollback()
                import_stats['failed'] += 1
    
    print(f"\n📊 Import complete: {import_stats['success']} success, {import_stats['failed']} failed")
    return import_stats


def train_intraday_models():
    """Train all intraday models"""
    
    print("\n" + "="*80)
    print("🚀 TRAINING INTRADAY MODELS")
    print("="*80 + "\n")
    
    all_jobs = []
    
    for symbol in all_symbols:
        for timeframe in intraday_timeframes:
            try:
                payload = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'epochs': 100,
                    'batch_size': 32,
                }
                
                response = requests.post(
                    f'{FREQAI_URL}/api/v1/train',
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    job_id = result.get('job_id', '?')
                    all_jobs.append({
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'job_id': job_id,
                    })
                    
                    # Print progress every 10 jobs
                    if len(all_jobs) % 10 == 0:
                        print(f"  {len(all_jobs)} jobs queued...")
                else:
                    print(f"  ⚠️  {symbol:12} {timeframe:3}  Error {response.status_code}")
                    
            except Exception as e:
                logger.error(f"  {symbol} {timeframe}: {str(e)[:40]}")
    
    print(f"\n✅ Total intraday jobs queued: {len(all_jobs)}/{len(all_symbols)*len(intraday_timeframes)}")
    return all_jobs


def check_intraday_results():
    """Check intraday model accuracy"""
    try:
        response = requests.get(f'{FREQAI_URL}/api/v1/models', timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch models: {response.status_code}")
            return
        
        models = response.json()
        
        # Filter for intraday models
        intraday_models = [m for m in models if 
                          m.get('is_deployed') and
                          m.get('symbol') in all_symbols and
                          m.get('timeframe') in intraday_timeframes]
        
        if not intraday_models:
            print("⚠️  No intraday models found yet")
            return
        
        intraday_models.sort(key=lambda x: (x['symbol'], x['timeframe']))
        
        print("="*80)
        print("📊 INTRADAY MODEL ACCURACY")
        print("="*80)
        print(f"{'Symbol':<12} {'TF':<6} {'Accuracy':<12} {'Status'}")
        print("-"*80)
        
        accuracies = []
        excellent = 0
        good = 0
        
        for model in intraday_models:
            acc = model.get('accuracy')
            if acc is not None:
                accuracies.append(acc)
                
                if acc >= 0.80:
                    status = "✅✅ EXCELLENT"
                    excellent += 1
                elif acc >= 0.70:
                    status = "✅ GOOD"
                    good += 1
                elif acc >= 0.60:
                    status = "⚠️  FAIR"
                else:
                    status = "❌ POOR"
                
                print(f"{model['symbol']:<12} {model['timeframe']:<6} {acc:.1%}        {status}")
        
        if accuracies:
            avg = sum(accuracies) / len(accuracies)
            
            print("\n" + "="*80)
            print(f"📈 Summary - Average Accuracy: {avg:.1%}")
            print(f"  ✅✅ Excellent (80%+):  {excellent}")
            print(f"  ✅ Good (70%+):        {good}")
            print(f"  Best/Worst:            {max(accuracies):.1%} / {min(accuracies):.1%}")
            print("="*80 + "\n")
        
    except Exception as e:
        print(f"❌ Error checking results: {e}\n")


def main():
    """Main execution"""
    try:
        # Import data
        import_intraday_data()
        
        # Train models
        jobs = train_intraday_models()
        
        if not jobs:
            print("⚠️  No training jobs were queued")
            return
        
        # Wait for training (longer for intraday)
        print(f"\n⏳ Waiting 240 seconds for {len(jobs)} intraday models to train...")
        time.sleep(240)
        
        # Check results
        check_intraday_results()
        
        print("✅ Intraday training complete!\n")
        
    except KeyboardInterrupt:
        print("\n⚠️  Training interrupted")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        db.close()


if __name__ == '__main__':
    main()
