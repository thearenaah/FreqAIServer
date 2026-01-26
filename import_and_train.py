#!/usr/bin/env python3
"""
Comprehensive training data import and model training script.
Focuses on Forex majors, Gold, and Major cryptocurrencies.
"""

import logging
import sys
from datetime import datetime
from market_data import MarketDataFetcher
from database import SessionLocal, TrainingData, Model
import requests
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Asset configuration
ASSETS_CONFIG = {
    'forex_majors': [
        'EUR/USD',
        'GBP/USD',
        'USD/JPY',
        'XAU/USD',  # Gold
        'AUD/USD',
        'USD/CAD',
        'USD/CHF',
        'GBP/JPY',
        'EUR/AUD',
        'GBP/AUD',
    ],
    'major_crypto': [
        'BTC/USD',
        'ETH/USD',
        'LTC/USD',
    ]
}

class TrainingDataImporter:
    def __init__(self):
        self.fetcher = MarketDataFetcher()
        self.db = SessionLocal()
        self.freqai_url = 'http://localhost:9000'
        self.import_stats = {
            'total_symbols': 0,
            'successful': 0,
            'failed': 0,
            'total_candles': 0
        }

    def import_asset_data(self, symbol: str, timeframe: str = '1h', limit: int = 500):
        """Import OHLCV data for a single asset."""
        try:
            logger.info(f"📊 Fetching {symbol} {timeframe} ({limit} candles)...")
            
            # Fetch from TwelveData
            candles = self.fetcher.fetch_ohlcv(symbol, timeframe, limit)
            
            if not candles:
                logger.warning(f"⚠️  No data returned for {symbol}")
                self.import_stats['failed'] += 1
                return False

            # Clear existing data for this symbol/timeframe
            deleted = self.db.query(TrainingData).filter(
                TrainingData.symbol == symbol,
                TrainingData.timeframe == timeframe
            ).delete()
            
            if deleted > 0:
                logger.info(f"  Cleared {deleted} existing candles for {symbol}")

            # Insert new training data
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
            logger.info(f"✅ Imported {len(candles)} candles for {symbol}")
            
            self.import_stats['successful'] += 1
            self.import_stats['total_candles'] += len(candles)
            return True

        except Exception as e:
            logger.error(f"❌ Error importing {symbol}: {str(e)}")
            self.db.rollback()
            self.import_stats['failed'] += 1
            return False

    def import_all_assets(self, timeframes: list = None):
        """Import data for all configured assets across multiple timeframes."""
        if timeframes is None:
            timeframes = ['1h']  # Default to 1h, can extend to ['1h', '4h', '1d']

        all_symbols = []
        for category, symbols in ASSETS_CONFIG.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Importing {category.upper()}")
            logger.info(f"{'='*60}")
            
            for symbol in symbols:
                self.import_stats['total_symbols'] += 1
                
                for timeframe in timeframes:
                    self.import_asset_data(symbol, timeframe)
                    time.sleep(0.5)  # Rate limit TwelveData
                
                all_symbols.append(symbol)

        return all_symbols

    def train_model(self, symbol: str, timeframe: str = '1h', limit: int = 500):
        """Trigger model training via FreqAI API."""
        try:
            logger.info(f"🚀 Training model for {symbol} {timeframe}...")
            
            response = requests.post(
                f'{self.freqai_url}/api/v1/train',
                json={
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'limit': limit
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Training started - Job ID: {result.get('job_id')}")
                return result
            else:
                logger.error(f"❌ Training failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ Error triggering training for {symbol}: {str(e)}")
            return None

    def train_all_models(self, symbols: list, timeframes: list = None):
        """Train models for all symbols."""
        if timeframes is None:
            timeframes = ['1h']

        logger.info(f"\n{'='*60}")
        logger.info("Starting Model Training")
        logger.info(f"{'='*60}\n")

        trained = 0
        for symbol in symbols:
            for timeframe in timeframes:
                result = self.train_model(symbol, timeframe)
                if result:
                    trained += 1
                time.sleep(1)  # Space out API calls

        return trained

    def check_model_status(self, symbols: list):
        """Check status of all trained models."""
        try:
            response = requests.get(
                f'{self.freqai_url}/api/v1/models',
                timeout=10
            )

            if response.status_code == 200:
                models = response.json()
                
                logger.info(f"\n{'='*60}")
                logger.info("Model Status Report")
                logger.info(f"{'='*60}\n")

                for model in models:
                    symbol = model.get('symbol', 'N/A')
                    if symbol in symbols:
                        status = "✅ DEPLOYED" if model.get('is_deployed') else "⏳ TRAINING"
                        accuracy = model.get('accuracy', 0)
                        logger.info(f"{status} | {symbol:12} | Accuracy: {accuracy:.2%}")

                return models
            else:
                logger.warning(f"Could not fetch model status: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error checking model status: {str(e)}")
            return None

    def print_summary(self, symbols_trained: int):
        """Print import and training summary."""
        logger.info(f"\n{'='*60}")
        logger.info("IMPORT & TRAINING SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total Symbols:   {self.import_stats['total_symbols']}")
        logger.info(f"Successful:      {self.import_stats['successful']}")
        logger.info(f"Failed:          {self.import_stats['failed']}")
        logger.info(f"Total Candles:   {self.import_stats['total_candles']:,}")
        logger.info(f"Models Trained:  {symbols_trained}")
        logger.info(f"{'='*60}\n")

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main execution."""
    logger.info("\n" + "="*60)
    logger.info("FreqAI Training Data Import & Model Training")
    logger.info("Focus: Forex Majors, Gold, Major Crypto")
    logger.info("="*60)

    importer = TrainingDataImporter()
    
    try:
        # Step 1: Import training data
        logger.info("\n📥 STEP 1: IMPORTING TRAINING DATA")
        logger.info("="*60)
        imported_symbols = importer.import_all_assets(timeframes=['1h'])

        # Step 2: Train models
        logger.info("\n🤖 STEP 2: TRAINING MODELS")
        logger.info("="*60)
        time.sleep(2)  # Wait before training
        trained_count = importer.train_all_models(imported_symbols, timeframes=['1h'])

        # Step 3: Check status
        logger.info("\n📈 STEP 3: CHECKING MODEL STATUS")
        logger.info("="*60)
        time.sleep(5)  # Give training time to start
        importer.check_model_status(imported_symbols)

        # Summary
        importer.print_summary(trained_count)

        logger.info("✅ Process completed!")
        logger.info("\n📊 Next steps:")
        logger.info("  1. Monitor training progress with: tail -f freqai.log")
        logger.info("  2. Check model status every 30 seconds")
        logger.info("  3. Once models deployed, start Celery worker")
        logger.info("  4. Signal generation will start automatically\n")

    except KeyboardInterrupt:
        logger.info("\n⚠️  Process interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {str(e)}")
        sys.exit(1)
    finally:
        importer.close()


if __name__ == '__main__':
    main()
