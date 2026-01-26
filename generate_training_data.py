"""
Generate synthetic training data using technical indicators
for FreqAIServer model training
"""
import numpy as np
from datetime import datetime, timedelta
from database import SessionLocal, TrainingData, Model
import logging

logger = logging.getLogger(__name__)

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    return np.mean(prices[-period:]) if len(prices) >= period else np.mean(prices)

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    if len(prices) < period:
        return 50
    
    deltas = np.diff(prices[-period-1:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    
    if avg_loss == 0:
        return 100 if avg_gain > 0 else 50
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def generate_signal_label(ema50, ema200, rsi):
    """
    Generate signal label based on technical indicators
    Returns: 'buy' (1), 'sell' (-1), or 'hold' (0)
    """
    ema_signal = 'up' if ema50 > ema200 else 'down'
    rsi_signal = 'overbought' if rsi > 70 else 'oversold' if rsi < 30 else 'neutral'
    
    if ema_signal == 'up' and rsi_signal != 'overbought':
        return 'buy'
    elif ema_signal == 'down' and rsi_signal != 'oversold':
        return 'sell'
    else:
        return 'hold'

def generate_training_data(symbol, timeframe, num_candles=500):
    """
    Generate synthetic training data using technical indicators
    """
    db = SessionLocal()
    
    try:
        # Generate synthetic OHLCV data
        base_price = 45000
        prices = []
        candles = []
        
        current_time = datetime.utcnow() - timedelta(hours=num_candles)
        
        for i in range(num_candles):
            # Random walk
            change = np.random.normal(0, 200)
            price = base_price + change + (i * 10)  # slight uptrend
            
            open_p = price + np.random.uniform(-100, 100)
            close_p = price + np.random.uniform(-100, 100)
            high_p = max(open_p, close_p) + np.random.uniform(0, 200)
            low_p = min(open_p, close_p) - np.random.uniform(0, 200)
            volume = np.random.uniform(1000, 10000)
            
            prices.append(close_p)
            
            candle = {
                'timestamp': current_time,
                'open': round(open_p, 2),
                'high': round(high_p, 2),
                'low': round(low_p, 2),
                'close': round(close_p, 2),
                'volume': round(volume, 2),
            }
            
            # Calculate indicators
            if len(prices) >= 50:
                ema50 = calculate_ema(prices, 50)
                ema200 = calculate_ema(prices, 200)
                rsi = calculate_rsi(prices)
                
                candle['ema50'] = round(ema50, 2)
                candle['ema200'] = round(ema200, 2)
                candle['rsi'] = round(rsi, 2)
                
                # Generate signal label
                signal = generate_signal_label(ema50, ema200, rsi)
                candle['signal'] = signal
                
                # Create training data record
                training_record = TrainingData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=current_time,
                    open=candle['open'],
                    high=candle['high'],
                    low=candle['low'],
                    close=candle['close'],
                    volume=candle['volume'],
                    indicators={
                        'ema50': candle['ema50'],
                        'ema200': candle['ema200'],
                        'rsi': candle['rsi'],
                        'signal': signal,
                    }
                )
                db.add(training_record)
            
            current_time += timedelta(hours=1)
        
        db.commit()
        logger.info(f"✅ Generated {num_candles} training records for {symbol} {timeframe}")
        
        # Create model record
        model = db.query(Model).filter(
            Model.symbol == symbol,
            Model.timeframe == timeframe
        ).first()
        
        if not model:
            model = Model(
                name=f"{symbol}_{timeframe}_v1",
                symbol=symbol,
                timeframe=timeframe,
                version=1,
                accuracy=0.75,  # Assumed accuracy for technical indicators
                is_active=True,
                is_deployed=True,
                trained_at=datetime.utcnow(),
                model_path=f"./models/{symbol}_{timeframe}.pkl"
            )
            db.add(model)
            db.commit()
            logger.info(f"✅ Created model: {model.name}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error generating training data: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    symbols_timeframes = [
        ("BTC/USDT", "1h"),
        ("ETH/USDT", "1h"),
        ("BTC/USDT", "4h"),
    ]
    
    for symbol, timeframe in symbols_timeframes:
        print(f"\n📊 Generating training data for {symbol} {timeframe}...")
        generate_training_data(symbol, timeframe, num_candles=500)
