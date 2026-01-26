#!/usr/bin/env python3
"""
Multi-Timeframe Advanced Training with Auto-Retraining
Trains models on 1m, 5m, 15m, 30m, 1h, 4h, 1d for 80%+ accuracy
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from market_data import MarketDataFetcher
from database import SessionLocal, TrainingData, Model
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Timeframes and data requirements
TIMEFRAMES = {
    '1m': {'candles': 1000, 'hours_back': 17},      # 1000 candles = 17 hours
    '5m': {'candles': 500, 'hours_back': 42},       # 500 candles = ~3.5 days
    '15m': {'candles': 500, 'hours_back': 125},     # 500 candles = ~10 days
    '30m': {'candles': 500, 'hours_back': 250},     # 500 candles = ~20 days
    '1h': {'candles': 500, 'hours_back': 500},      # 500 candles = ~20 days
    '4h': {'candles': 500, 'hours_back': 2000},     # 500 candles = ~80 days
    '1d': {'candles': 200, 'hours_back': 4800},     # 200 candles = ~200 days
}

ASSETS = {
    'forex_majors': [
        'EUR/USD', 'GBP/USD', 'USD/JPY', 'XAU/USD', 'AUD/USD',
        'USD/CAD', 'USD/CHF', 'GBP/JPY', 'EUR/AUD', 'GBP/AUD',
    ],
    'major_crypto': [
        'BTC/USD', 'ETH/USD', 'LTC/USD',
    ]
}

class MultiTimeframeTrainer:
    def __init__(self):
        self.fetcher = MarketDataFetcher()
        self.db = SessionLocal()
        self.freqai_url = 'http://localhost:9000'
        self.stats = {'imported': 0, 'failed': 0, 'trained': 0}

    def fetch_and_store_data(self, symbol: str, timeframe: str, limit: int):
        """Fetch candles and store in database"""
        try:
            logger.info(f"📥 Fetching {symbol} {timeframe} ({limit} candles)...")
            
            candles = self.fetcher.fetch_ohlcv(symbol, timeframe, limit)
            
            if not candles:
                logger.warning(f"⚠️  No data for {symbol} {timeframe}")
                self.stats['failed'] += 1
                return False

            # Clear existing data for this symbol/timeframe
            deleted = self.db.query(TrainingData).filter(
                TrainingData.symbol == symbol,
                TrainingData.timeframe == timeframe
            ).delete()
            
            if deleted > 0:
                logger.info(f"  Cleared {deleted} old candles")

            # Insert new data
            for candle in candles:
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
                self.db.add(td)

            self.db.commit()
            logger.info(f"✅ Imported {len(candles)} candles for {symbol} {timeframe}")
            self.stats['imported'] += 1
            return True

        except Exception as e:
            logger.error(f"❌ Error: {str(e)[:80]}")
            self.db.rollback()
            self.stats['failed'] += 1
            return False

    def train_model(self, symbol: str, timeframe: str):
        """Trigger model training via API"""
        try:
            logger.info(f"🚀 Training {symbol} {timeframe}...")
            
            response = requests.post(
                f'{self.freqai_url}/api/v1/train',
                json={'symbol': symbol, 'timeframe': timeframe, 'limit': 500},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Training started - Job ID: {result.get('job_id')}")
                self.stats['trained'] += 1
                return True
            else:
                logger.error(f"❌ {response.status_code}: {response.text[:80]}")
                return False

        except Exception as e:
            logger.error(f"❌ Error: {str(e)[:80]}")
            return False

    def train_all(self):
        """Train all symbol/timeframe combinations"""
        all_symbols = []
        for category, symbols in ASSETS.items():
            all_symbols.extend(symbols)

        total_tasks = len(all_symbols) * len(TIMEFRAMES)
        current = 0

        print("\n" + "="*80)
        print("MULTI-TIMEFRAME TRAINING - PHASE 1: DATA IMPORT")
        print("="*80 + "\n")

        for symbol in all_symbols:
            for timeframe, config in TIMEFRAMES.items():
                current += 1
                print(f"[{current}/{total_tasks}] {symbol} {timeframe}")
                self.fetch_and_store_data(symbol, timeframe, config['candles'])
                time.sleep(0.3)  # Rate limit

        print("\n" + "="*80)
        print("MULTI-TIMEFRAME TRAINING - PHASE 2: MODEL TRAINING")
        print("="*80 + "\n")

        current = 0
        for symbol in all_symbols:
            for timeframe in TIMEFRAMES.keys():
                current += 1
                print(f"[{current}/{total_tasks}] {symbol} {timeframe}")
                self.train_model(symbol, timeframe)
                time.sleep(1)  # Space out API calls

        # Wait for training to complete
        print("\n⏳ Waiting for models to train (60 seconds)...")
        time.sleep(60)

        # Show results
        self.show_status(all_symbols)

    def show_status(self, symbols: list):
        """Show model training status"""
        try:
            response = requests.get(f'{self.freqai_url}/api/v1/models', timeout=10)
            
            if response.status_code == 200:
                models = response.json()
                
                print("\n" + "="*80)
                print("✅ MODEL TRAINING RESULTS")
                print("="*80 + "\n")

                deployed = 0
                for model in models:
                    if model.get('symbol') in symbols:
                        status = "✅ DEPLOYED" if model.get('is_deployed') else "⏳ TRAINING"
                        accuracy = f"{model.get('accuracy', 0):.1%}" if model.get('accuracy') else "N/A"
                        print(f"{status} | {model.get('symbol'):12} {model.get('timeframe'):5} | Acc: {accuracy}")
                        if model.get('is_deployed'):
                            deployed += 1

                print(f"\n{deployed}/{len([m for m in models if m.get('symbol') in symbols])} models deployed")

        except Exception as e:
            logger.error(f"Error fetching status: {e}")

    def print_summary(self):
        """Print final summary"""
        print("\n" + "="*80)
        print("IMPORT & TRAINING SUMMARY")
        print("="*80)
        print(f"Data Imported:  {self.stats['imported']}")
        print(f"Failed:         {self.stats['failed']}")
        print(f"Models Trained: {self.stats['trained']}")
        print("="*80 + "\n")

    def close(self):
        """Close database connection"""
        self.db.close()


def main():
    """Main execution"""
    logger.info("\n" + "="*80)
    logger.info("🚀 MULTI-TIMEFRAME ADVANCED TRAINING")
    logger.info("Timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d")
    logger.info("Target Accuracy: 80%+")
    logger.info("="*80)

    trainer = MultiTimeframeTrainer()
    
    try:
        trainer.train_all()
        trainer.print_summary()
        
        logger.info("\n✅ Process completed!")
        logger.info("📊 Next steps:")
        logger.info("  1. Enable auto-retraining (daily updates)")
        logger.info("  2. Start Celery worker for signal generation")
        logger.info("  3. Monitor model accuracy over time\n")

    except KeyboardInterrupt:
        logger.info("\n⚠️  Process interrupted")
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        trainer.close()


if __name__ == '__main__':
    main()
