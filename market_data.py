"""
Market data fetcher - pulls OHLCV data from multiple sources
"""
import ccxt
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio
import pandas as pd
from sqlalchemy.orm import Session

from database import SessionLocal, TrainingData
from config import CCXT_EXCHANGE


class MarketDataFetcher:
    """Fetch market data from various sources"""
    
    def __init__(self):
        self.exchange = getattr(ccxt, CCXT_EXCHANGE)()
        
    def fetch_ohlcv_ccxt(
        self, 
        symbol: str, 
        timeframe: str = "1h", 
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch OHLCV data from CCXT exchange
        symbol: BTC/USDT
        timeframe: 1m, 5m, 1h, 4h, 1d
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            data = []
            for candle in ohlcv:
                data.append({
                    'timestamp': datetime.fromtimestamp(candle[0] / 1000),
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5],
                })
            return data
        except Exception as e:
            print(f"Error fetching {symbol} from {CCXT_EXCHANGE}: {e}")
            return []
    
    def fetch_ohlcv_yfinance(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1h"
    ) -> List[Dict]:
        """
        Fetch OHLCV data from Yahoo Finance
        symbol: AAPL, GOOGL, etc.
        period: 1d, 1mo, 1y
        interval: 1m, 5m, 15m, 1h, 1d
        """
        try:
            data_yf = yf.download(symbol, period=period, interval=interval, progress=False)
            
            data = []
            for idx, row in data_yf.iterrows():
                data.append({
                    'timestamp': idx,
                    'open': row['Open'],
                    'high': row['High'],
                    'low': row['Low'],
                    'close': row['Close'],
                    'volume': row['Volume'],
                })
            return data
        except Exception as e:
            print(f"Error fetching {symbol} from Yahoo Finance: {e}")
            return []
    
    async def store_training_data(
        self,
        db: Session,
        symbol: str,
        timeframe: str,
        ohlcv_data: List[Dict]
    ) -> int:
        """Store fetched data in database"""
        count = 0
        for candle in ohlcv_data:
            # Check if already exists
            existing = db.query(TrainingData).filter(
                TrainingData.symbol == symbol,
                TrainingData.timeframe == timeframe,
                TrainingData.timestamp == candle['timestamp']
            ).first()
            
            if not existing:
                training_data = TrainingData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candle['timestamp'],
                    open=candle['open'],
                    high=candle['high'],
                    low=candle['low'],
                    close=candle['close'],
                    volume=candle['volume'],
                )
                db.add(training_data)
                count += 1
        
        db.commit()
        return count
    
    async def sync_market_data(
        self,
        symbols: List[str],
        timeframes: List[str] = ["1h", "4h", "1d"],
        lookback_days: int = 30
    ):
        """
        Periodically sync market data for all symbols
        """
        db = SessionLocal()
        try:
            for symbol in symbols:
                for timeframe in timeframes:
                    # Fetch from CCXT for crypto
                    if '/' in symbol:  # Crypto pair
                        ohlcv_data = self.fetch_ohlcv_ccxt(symbol, timeframe)
                    else:  # Stock symbol
                        ohlcv_data = self.fetch_ohlcv_yfinance(symbol)
                    
                    if ohlcv_data:
                        await self.store_training_data(db, symbol, timeframe, ohlcv_data)
                        print(f"Synced {len(ohlcv_data)} candles for {symbol} {timeframe}")
        finally:
            db.close()


if __name__ == "__main__":
    fetcher = MarketDataFetcher()
    
    # Example: Fetch Bitcoin data
    data = fetcher.fetch_ohlcv_ccxt("BTC/USDT", "1h", 100)
    print(f"Fetched {len(data)} candles")
