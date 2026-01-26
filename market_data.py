"""
Market data fetcher - pulls OHLCV data from multiple sources
Primary source: TwelveData API (supports crypto, forex, stocks)
Fallback: CCXT and Yahoo Finance
"""
import requests
import ccxt
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio
import pandas as pd
import os
from sqlalchemy.orm import Session

from database import SessionLocal, TrainingData
from config import CCXT_EXCHANGE


class MarketDataFetcher:
    """Fetch market data from TwelveData (primary) or fallback sources"""
    
    def __init__(self):
        self.twelve_api_key = os.getenv('TWELVE_DATA_API_KEY', '')
        self.twelve_base_url = "https://api.twelvedata.com"
        self.exchange = getattr(ccxt, CCXT_EXCHANGE)() if CCXT_EXCHANGE else None
        
    def fetch_ohlcv_twelvedata(
        self,
        symbol: str,
        interval: str = "1h",
        output_size: int = 500
    ) -> List[Dict]:
        """
        Fetch OHLCV data from TwelveData API
        Supports: crypto, forex, stocks, etfs, indices
        
        Args:
            symbol: Symbol (BTC/USD, EUR/USD, AAPL, etc.)
            interval: 1min, 5min, 15min, 30min, 1h, 4h, 1day, 1week, 1month
            output_size: Number of candles (max 5000)
        
        Returns:
            List of OHLCV candles
        """
        if not self.twelve_api_key:
            print("Error: TWELVE_DATA_API_KEY not set in environment")
            return []
        
        try:
            # TwelveData expects different formats based on symbol type
            # Crypto: Keep slash format (BTC/USD)
            # Forex: Keep slash format (EUR/USD)
            # Stocks: No slash (AAPL)
            api_symbol = symbol
            
            # Just use symbol as-is, TwelveData handles the formatting
            params = {
                'symbol': api_symbol,
                'interval': interval,
                'outputsize': min(output_size, 5000),
                'apikey': self.twelve_api_key,
                'order': 'asc'  # Oldest first
            }
            
            print(f"Requesting TwelveData: {api_symbol} interval={interval}")
            response = requests.get(
                f"{self.twelve_base_url}/time_series",
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"TwelveData error {response.status_code}: {response.text}")
                return []
            
            data_json = response.json()
            
            if 'status' in data_json and data_json['status'] != 'ok':
                print(f"TwelveData API error: {data_json.get('message', 'Unknown error')}")
                return []
            
            # TwelveData returns 'values' not 'data'
            values = data_json.get('values') or data_json.get('data')
            if not values:
                print(f"No data in TwelveData response for {api_symbol}")
                return []
            
            data = []
            for candle in values:
                try:
                    data.append({
                        'timestamp': datetime.fromisoformat(candle['datetime'].replace('Z', '+00:00')),
                        'open': float(candle['open']),
                        'high': float(candle['high']),
                        'low': float(candle['low']),
                        'close': float(candle['close']),
                        'volume': float(candle.get('volume', 0)),
                    })
                except (ValueError, KeyError) as e:
                    print(f"Error parsing candle: {e}, skipping")
                    continue
            
            return data
            
        except requests.exceptions.Timeout:
            print(f"TwelveData request timeout for {symbol}")
            return []
        except Exception as e:
            print(f"Error fetching {symbol} from TwelveData: {e}")
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
    
    def fetch_ohlcv(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 500
    ) -> List[Dict]:
        """
        Fetch OHLCV data using TwelveData API only
        Supports: crypto (BTC/USD, ETH/USD), forex (EUR/USD), stocks (AAPL)
        
        Args:
            symbol: Symbol (BTC/USD, EUR/USD, AAPL, etc.)
            interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo (converts to TwelveData format)
            limit: Number of candles
        
        Returns:
            List of OHLCV candles
        """
        # Map common interval formats to TwelveData format
        interval_map = {
            '1m': '1min',
            '5m': '5min',
            '15m': '15min',
            '30m': '30min',
            '1h': '1h',
            '4h': '4h',
            '1d': '1day',
            '1w': '1week',
            '1mo': '1month',
        }
        
        # Convert interval if needed
        twelve_interval = interval_map.get(interval, interval)
        
        return self.fetch_ohlcv_twelvedata(symbol, twelve_interval, limit)
    
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
    
    # Example: Fetch data (TwelveData primary, with fallbacks)
    print("\n=== Fetching Crypto ===")
    btc_data = fetcher.fetch_ohlcv("BTC/USDT", "1h", 100)
    print(f"Fetched {len(btc_data)} BTC candles\n")
    
    print("=== Fetching Forex ===")
    eur_data = fetcher.fetch_ohlcv("EUR/USD", "1h", 100)
    print(f"Fetched {len(eur_data)} EUR/USD candles\n")
    
    print("=== Fetching Stock ===")
    aapl_data = fetcher.fetch_ohlcv("AAPL", "1h", 100)
    print(f"Fetched {len(aapl_data)} AAPL candles")
