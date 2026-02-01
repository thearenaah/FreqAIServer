"""
Enhanced Feature Engineering for Improved Day Trading Strategy
Calculates all technical indicators and features for ML model training

Indicators:
- EMA (13, 50, 200)
- RSI (14)
- MACD
- Bollinger Bands
- ATR (volatility)
- ADX (trend strength)
- Volume Profile
- Price Action patterns
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import ta


class ImprovedFeatureEngineer:
    """Enhanced feature calculations for day trading ML model"""
    
    # EMA Periods for different timeframes
    EMA_PERIODS = {
        '1m': [5, 13, 50],
        '5m': [13, 50, 200],
        '15m': [13, 50, 200],
        '1h': [13, 50, 200],
        '4h': [20, 50, 200],
        '1d': [12, 26, 200]
    }
    
    @staticmethod
    def calculate_ema(close: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average"""
        return pd.Series(close).ewm(span=period, adjust=False).mean().values
    
    @staticmethod
    def calculate_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index - measures momentum"""
        delta = np.diff(close, prepend=close[0])
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = pd.Series(gain).rolling(window=period, min_periods=1).mean().values
        avg_loss = pd.Series(loss).rolling(window=period, min_periods=1).mean().values
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple:
        """
        MACD - Identifies trend and momentum changes
        Returns: (macd_line, signal_line, histogram)
        """
        ema_fast = pd.Series(close).ewm(span=fast, adjust=False).mean().values
        ema_slow = pd.Series(close).ewm(span=slow, adjust=False).mean().values
        
        macd_line = ema_fast - ema_slow
        signal_line = pd.Series(macd_line).ewm(span=signal, adjust=False).mean().values
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        Average True Range - volatility measure
        Used for SL/TP sizing and stop placement
        """
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = pd.Series(true_range).rolling(window=period, min_periods=1).mean().values
        
        return atr
    
    @staticmethod
    def calculate_bollinger_bands(close: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Dict[str, np.ndarray]:
        """
        Bollinger Bands - identifies overbought/oversold conditions and volatility
        Returns: upper, middle (SMA), lower bands
        """
        sma = pd.Series(close).rolling(window=period, min_periods=1).mean().values
        std = pd.Series(close).rolling(window=period, min_periods=1).std().values
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return {
            'upper': upper,
            'middle': sma,
            'lower': lower,
            'width': upper - lower,
            'position': (close - lower) / (upper - lower)  # 0-1: position in band
        }
    
    @staticmethod
    def calculate_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        Average Directional Index - measures trend strength
        0-20: Weak trend, 20-40: Strong, 40+: Very Strong
        """
        # Calculate +DM and -DM
        high_diff = np.diff(high, prepend=high[0])
        low_diff = -np.diff(low, prepend=low[0])
        
        pos_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        neg_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
        
        # True Range
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # Smoothed values
        pos_dm_smooth = pd.Series(pos_dm).rolling(window=period, min_periods=1).sum().values
        neg_dm_smooth = pd.Series(neg_dm).rolling(window=period, min_periods=1).sum().values
        tr_smooth = pd.Series(tr).rolling(window=period, min_periods=1).sum().values
        
        # DI+, DI-
        di_plus = 100 * (pos_dm_smooth / (tr_smooth + 1e-10))
        di_minus = 100 * (neg_dm_smooth / (tr_smooth + 1e-10))
        
        # DX and ADX
        dx = 100 * (np.abs(di_plus - di_minus) / (di_plus + di_minus + 1e-10))
        adx = pd.Series(dx).rolling(window=period, min_periods=1).mean().values
        
        return adx
    
    @staticmethod
    def calculate_rvi(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        Relative Vigor Index - measures conviction of recent price action
        Similar to RSI but uses open/close relationship
        """
        numerator = (close - open) if hasattr(close, '__len__') else close
        denominator = high - low + 1e-10
        
        # Smooth the ratio
        rvi = 100 * pd.Series(numerator / denominator).rolling(window=period, min_periods=1).mean().values
        return np.clip(rvi, 0, 100)
    
    @staticmethod
    def detect_candle_pattern(open_: float, high: float, low: float, close: float, prev_close: float = None) -> Dict[str, float]:
        """
        Detect Japanese candlestick patterns
        
        Returns confidence scores (0-1) for:
        - Hammer: Small body, long lower wick (bullish reversal)
        - Engulfing: Current candle fully contains previous
        - Doji: Open ≈ Close (indecision)
        - Marubozu: No wicks (strong conviction)
        """
        body = abs(close - open_)
        wick_upper = high - max(open_, close)
        wick_lower = min(open_, close) - low
        range_ = high - low
        
        patterns = {}
        
        # Hammer/Inverted Hammer
        if wick_lower > body * 2 and wick_upper < body * 0.5:
            patterns['hammer'] = min(1.0, wick_lower / range_)
        else:
            patterns['hammer'] = 0.0
        
        # Doji (indecision)
        if body < range_ * 0.1:  # Body < 10% of range
            patterns['doji'] = 1.0
        else:
            patterns['doji'] = 0.0
        
        # Marubozu (no wicks, strong conviction)
        if wick_upper < range_ * 0.05 and wick_lower < range_ * 0.05:
            patterns['marubozu'] = 1.0
        else:
            patterns['marubozu'] = 0.0
        
        # Spinning Top (indecision, but with wicks)
        if body < range_ * 0.3 and wick_upper > body and wick_lower > body:
            patterns['spinning_top'] = min(1.0, (wick_upper + wick_lower) / (2 * range_))
        else:
            patterns['spinning_top'] = 0.0
        
        return patterns
    
    @staticmethod
    def detect_price_action(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        lookback: int = 5
    ) -> Dict[str, float]:
        """
        Detect price action patterns
        
        Returns:
        - higher_high: Recent high > prior high
        - higher_low: Recent low > prior low
        - lower_high: Recent high < prior high
        - lower_low: Recent low < prior low
        - inside_bar: Recent range < prior range
        """
        if len(highs) < lookback + 1:
            return {}
        
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        
        patterns = {}
        
        # Trend confirmation
        patterns['higher_high'] = 1.0 if np.all(np.diff(recent_highs) > 0) else 0.0
        patterns['higher_low'] = 1.0 if np.all(np.diff(recent_lows) > 0) else 0.0
        patterns['lower_high'] = 1.0 if np.all(np.diff(recent_highs) < 0) else 0.0
        patterns['lower_low'] = 1.0 if np.all(np.diff(recent_lows) < 0) else 0.0
        
        # Inside bar (range compression)
        recent_range = recent_highs[-1] - recent_lows[-1]
        prev_range = recent_highs[-2] - recent_lows[-2]
        patterns['inside_bar'] = 1.0 if recent_range < prev_range else 0.0
        
        return patterns
    
    @staticmethod
    def calculate_volume_features(volume: np.ndarray, period: int = 20) -> Dict[str, np.ndarray]:
        """
        Calculate volume-based features
        
        - Volume trend (SMA)
        - Volume spike detection
        - Volume rate of change
        """
        vol_sma = pd.Series(volume).rolling(window=period, min_periods=1).mean().values
        vol_roc = ((volume - vol_sma) / vol_sma) * 100
        
        return {
            'volume_sma': vol_sma,
            'volume_roc': vol_roc,
            'volume_spike': vol_roc > 50  # 50% above average
        }
    
    @staticmethod
    def calculate_momentum(close: np.ndarray, period: int = 10) -> np.ndarray:
        """
        Momentum indicator - rate of price change
        Useful for identifying acceleration/deceleration
        """
        momentum = close - np.roll(close, period)
        return momentum
    
    def engineer_features(
        self,
        df: pd.DataFrame,
        timeframe: str = '15m'
    ) -> pd.DataFrame:
        """
        Calculate ALL features for ML model
        
        Input DataFrame should have: open, high, low, close, volume
        
        Output adds columns for:
        - EMAs (13, 50, 200)
        - RSI, MACD, ADX
        - ATR, Bollinger Bands
        - Volume features
        - Price action patterns
        - Candle patterns
        - Momentum
        """
        df = df.copy()
        
        # Basic OHLCV
        open_ = df['open'].values
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        volume = df['volume'].values
        
        # EMAs
        ema_periods = self.EMA_PERIODS.get(timeframe, [13, 50, 200])
        for period in ema_periods:
            df[f'ema_{period}'] = self.calculate_ema(close, period)
        
        # RSI
        df['rsi_14'] = self.calculate_rsi(close, 14)
        
        # MACD
        macd, signal, histogram = self.calculate_macd(close)
        df['macd'] = macd
        df['macd_signal'] = signal
        df['macd_histogram'] = histogram
        
        # ATR (volatility)
        df['atr_14'] = self.calculate_atr(high, low, close, 14)
        
        # Bollinger Bands
        bb = self.calculate_bollinger_bands(close, 20, 2.0)
        df['bb_upper'] = bb['upper']
        df['bb_middle'] = bb['middle']
        df['bb_lower'] = bb['lower']
        df['bb_width'] = bb['width']
        df['bb_position'] = bb['position']
        
        # ADX (trend strength)
        df['adx_14'] = self.calculate_adx(high, low, close, 14)
        
        # Volume features
        vol_features = self.calculate_volume_features(volume, 20)
        df['volume_sma'] = vol_features['volume_sma']
        df['volume_roc'] = vol_features['volume_roc']
        df['volume_spike'] = vol_features['volume_spike'].astype(float)
        
        # Momentum
        df['momentum_10'] = self.calculate_momentum(close, 10)
        
        # Price Action patterns (multi-candle)
        pa_patterns = self.detect_price_action(high, low, close, lookback=5)
        for pattern, value in pa_patterns.items():
            df[f'pa_{pattern}'] = float(value)
        
        # Candle patterns (current candle)
        # For each row, check current candle pattern
        candle_patterns_list = []
        for i in range(len(df)):
            if i == 0:
                prev_close = open_[0]
            else:
                prev_close = close[i-1]
            
            pattern = self.detect_candle_pattern(open_[i], high[i], low[i], close[i], prev_close)
            candle_patterns_list.append(pattern)
        
        # Add candle patterns to dataframe
        pattern_names = ['hammer', 'doji', 'marubozu', 'spinning_top']
        for pattern_name in pattern_names:
            df[f'candle_{pattern_name}'] = [p.get(pattern_name, 0) for p in candle_patterns_list]
        
        # Fill NaN values
        df = df.fillna(method='bfill').fillna(method='ffill')
        
        return df
