"""
Feature engineering - Calculate technical indicators and ML features
Professional Grade Trading Strategy: EMA + Pivot Points + Fibonacci + RSI + Candle Patterns
"""
import pandas as pd
import numpy as np
from typing import Dict, List
import ta  # Technical Analysis library

from pivot_points import PivotPoints
from candle_patterns import CandlePatterns
from fibonacci_levels import FibonacciLevels
from strategy_rules import StrategyEngine, StrategyRules


class FeatureEngineer:
    """Calculate features for ML models - Professional Grade Strategy"""
    
    def __init__(self, strategy_rules: StrategyRules = None):
        self.rules = strategy_rules or StrategyRules()
        self.strategy_engine = StrategyEngine(self.rules)
    
    @staticmethod
    def calculate_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index"""
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = pd.Series(gain).rolling(window=period).mean().values
        avg_loss = pd.Series(loss).rolling(window=period).mean().values
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(close: np.ndarray) -> tuple:
        """Moving Average Convergence Divergence"""
        ema12 = pd.Series(close).ewm(span=12).mean().values
        ema26 = pd.Series(close).ewm(span=26).mean().values
        
        macd = ema12 - ema26
        signal = pd.Series(macd).ewm(span=9).mean().values
        histogram = macd - signal
        
        return macd, signal, histogram
    
    @staticmethod
    def calculate_bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2):
        """Bollinger Bands"""
        sma = pd.Series(close).rolling(window=period).mean().values
        std = pd.Series(close).rolling(window=period).std().values
        
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        
        return upper, sma, lower
    
    @staticmethod
    def calculate_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14):
        """Average True Range"""
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = pd.Series(tr).rolling(window=period).mean().values
        
        return atr
    
    @staticmethod
    def calculate_price_features(df: pd.DataFrame) -> Dict[str, float]:
        """Calculate price-based features"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        features = {}
        
        # Trend features
        features['sma_20'] = pd.Series(close).rolling(window=20).mean().iloc[-1]
        features['sma_50'] = pd.Series(close).rolling(window=50).mean().iloc[-1]
        features['sma_200'] = pd.Series(close).rolling(window=200).mean().iloc[-1]
        
        # Momentum features
        rsi = FeatureEngineer.calculate_rsi(close)
        features['rsi_14'] = rsi[-1]
        
        # MACD
        macd, signal, histogram = FeatureEngineer.calculate_macd(close)
        features['macd'] = macd[-1]
        features['macd_signal'] = signal[-1]
        features['macd_histogram'] = histogram[-1]
        
        # Bollinger Bands
        upper, sma, lower = FeatureEngineer.calculate_bollinger_bands(close)
        features['bb_upper'] = upper[-1]
        features['bb_middle'] = sma[-1]
        features['bb_lower'] = lower[-1]
        features['bb_position'] = (close[-1] - lower[-1]) / (upper[-1] - lower[-1]) if upper[-1] != lower[-1] else 0.5
        
        # ATR
        atr = FeatureEngineer.calculate_atr(high, low, close)
        features['atr'] = atr[-1]
        
        # Volume features
        features['volume_sma'] = pd.Series(volume).rolling(window=20).mean().iloc[-1]
        features['volume_ratio'] = volume[-1] / features['volume_sma'] if features['volume_sma'] > 0 else 1.0
        
        # Price features
        features['price_change'] = (close[-1] - close[-20]) / close[-20] if close[-20] > 0 else 0
        features['volatility'] = np.std(close[-20:])
        
        # Return features
        returns = np.diff(close) / close[:-1]
        features['returns_mean'] = np.mean(returns[-20:])
        features['returns_std'] = np.std(returns[-20:])
        
        # PROFESSIONAL: EMA-based features
        ema_50 = pd.Series(close).ewm(span=50, adjust=False).mean().iloc[-1]
        ema_200 = pd.Series(close).ewm(span=200, adjust=False).mean().iloc[-1]
        
        features['ema_50'] = ema_50
        features['ema_200'] = ema_200
        features['ema_50_above_200'] = 1.0 if ema_50 > ema_200 else 0.0
        features['price_above_ema_50'] = 1.0 if close[-1] > ema_50 else 0.0
        features['distance_to_ema_50'] = (close[-1] - ema_50) / ema_50 if ema_50 > 0 else 0
        
        return features
    
    def calculate_professional_features(
        self,
        df: pd.DataFrame,
        include_patterns: bool = True,
        include_fibonacci: bool = True
    ) -> Dict[str, any]:
        """
        Calculate professional trading features including:
        - EMA 50/200 support/resistance
        - Pivot points
        - Fibonacci retracement levels
        - RSI conditions
        - Candle patterns
        - Strategy rules evaluation
        - Confluence detection (multiple levels aligning)
        """
        if len(df) < self.rules.ema_slow:
            return {}
        
        features = {}
        
        # Base features
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        current_price = close[-1]
        current_high = high[-1]
        current_low = low[-1]
        current_open = df['open'].values[-1]
        
        # Calculate EMAs
        ema_50 = pd.Series(close).ewm(span=self.rules.ema_fast, adjust=False).mean().iloc[-1]
        ema_200 = pd.Series(close).ewm(span=self.rules.ema_slow, adjust=False).mean().iloc[-1]
        
        features['ema_50'] = ema_50
        features['ema_200'] = ema_200
        features['ema_trend'] = 1.0 if ema_50 > ema_200 else -1.0
        
        # Calculate RSI
        rsi = self.calculate_rsi(close, self.rules.rsi_period)[-1]
        features['rsi'] = rsi
        
        # Calculate Pivot Points
        if len(df) >= 1:
            prev_high = high[-2] if len(df) >= 2 else high[-1]
            prev_low = low[-2] if len(df) >= 2 else low[-1]
            prev_close = close[-2] if len(df) >= 2 else close[-1]
        
        pivot_data = PivotPoints.calculate_floor_pivot(prev_high, prev_low, prev_close)
        features['pivot_points'] = pivot_data
        
        # Calculate Fibonacci Retracement Levels
        if include_fibonacci and self.rules.use_fibonacci:
            try:
                # Identify recent swing high and low
                lookback = min(50, len(close) - 1)
                recent_high = np.max(high[-lookback:])
                recent_low = np.min(low[-lookback:])
                
                if recent_high > recent_low:
                    fibonacci_data = FibonacciLevels.calculate_retracements(
                        recent_high, recent_low, include_extensions=True
                    )
                    features['fibonacci_levels'] = fibonacci_data
                    
                    # Analyze if price is at Fibonacci level
                    fib_analysis = FibonacciLevels.analyze_price_action_at_fibonacci(
                        current_price, fibonacci_data, self.rules.fibonacci_tolerance
                    )
                    features['fibonacci_analysis'] = fib_analysis
                    
                    # Check for Fibonacci bounce
                    fib_bounce = FibonacciLevels.identify_fibonacci_bounce(
                        current_price,
                        close[-2] if len(close) >= 2 else close[-1],
                        recent_high,
                        recent_low
                    )
                    features['fibonacci_bounce'] = fib_bounce
            except Exception as e:
                print(f"Warning: Fibonacci calculation failed: {e}")
                features['fibonacci_levels'] = {}
                features['fibonacci_analysis'] = {}
                features['fibonacci_bounce'] = {}
        
        # Candle patterns (if enabled)
        if include_patterns and len(df) >= 2:
            patterns = CandlePatterns.detect_patterns(
                open_price=current_open,
                high=current_high,
                low=current_low,
                close=current_price,
                prev_open=df['open'].values[-2],
                prev_high=high[-2],
                prev_low=low[-2],
                prev_close=close[-2],
            )
            features['candle_patterns'] = patterns
        
        # Recent price action (last 3-5 candles)
        lookback = min(5, len(df) - 1)
        recent_high = np.max(high[-lookback:])
        recent_low = np.min(low[-lookback:])
        
        recent_action = {
            'current_price': current_price,
            'highest_price': recent_high,
            'lowest_price': recent_low,
            'range': recent_high - recent_low,
        }
        features['recent_price_action'] = recent_action
        
        # Evaluate strategy rules
        if include_patterns:
            # Get Fibonacci data for strategy evaluation
            fibonacci_data = features.get('fibonacci_levels', {})
            
            long_signal, long_conf, long_reasons = self.strategy_engine.check_long_signal(
                price=current_price,
                ema_50=ema_50,
                ema_200=ema_200,
                rsi=rsi,
                pivot_data=pivot_data,
                candle_patterns=features.get('candle_patterns'),
                recent_price_action=recent_action,
            )
            
            short_signal, short_conf, short_reasons = self.strategy_engine.check_short_signal(
                price=current_price,
                ema_50=ema_50,
                ema_200=ema_200,
                rsi=rsi,
                pivot_data=pivot_data,
                candle_patterns=features.get('candle_patterns'),
                recent_price_action=recent_action,
            )
            
            # Evaluate Fibonacci and Pivot Point confluence
            confluence = self.strategy_engine.evaluate_fibonacci_confluence(
                price=current_price,
                fibonacci_data=fibonacci_data,
                pivot_data=pivot_data,
                ema_50=ema_50,
                ema_200=ema_200
            )
            
            # Calculate TP/SL levels for LONG and SHORT signals
            long_tp_sl = None
            short_tp_sl = None
            
            if long_signal.value == 'buy' and long_conf >= 0.50:
                # Get support level for LONG trade
                support_level = pivot_data.get('s1', current_price * 0.99)
                try:
                    long_tp_sl = self.strategy_engine.calculate_long_tp_sl(
                        entry_price=current_price,
                        support_level=support_level,
                        pivot_data=pivot_data,
                        fibonacci_data=fibonacci_data,
                        atr=features.get('atr', None),
                        highest_recent=recent_high,
                    )
                except Exception as e:
                    long_tp_sl = {'error': str(e)}
            
            if short_signal.value == 'sell' and short_conf >= 0.50:
                # Get resistance level for SHORT trade
                resistance_level = pivot_data.get('r1', current_price * 1.01)
                try:
                    short_tp_sl = self.strategy_engine.calculate_short_tp_sl(
                        entry_price=current_price,
                        resistance_level=resistance_level,
                        pivot_data=pivot_data,
                        fibonacci_data=fibonacci_data,
                        atr=features.get('atr', None),
                        lowest_recent=recent_low,
                    )
                except Exception as e:
                    short_tp_sl = {'error': str(e)}
            
            features['signal_analysis'] = {
                'long_signal': long_signal.value,
                'long_confidence': long_conf,
                'long_reasons': long_reasons,
                'long_tp_sl': long_tp_sl,
                'short_signal': short_signal.value,
                'short_confidence': short_conf,
                'short_reasons': short_reasons,
                'short_tp_sl': short_tp_sl,
                'confluence': confluence,
                'confluence_strength': confluence['confluence_level'],
                'confluence_reason': confluence['confluence_reason'],
            }
        
        return features
    
    @staticmethod
    def get_feature_columns() -> List[str]:
        """Get list of all feature column names"""
        return [
            'sma_20', 'sma_50', 'sma_200',
            'rsi_14',
            'macd', 'macd_signal', 'macd_histogram',
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_position',
            'atr',
            'volume_sma', 'volume_ratio',
            'price_change', 'volatility',
            'returns_mean', 'returns_std'
        ]


if __name__ == "__main__":
    # Example usage
    import yfinance as yf
    
    data = yf.download("AAPL", period="3mo", interval="1d")
    
    df = pd.DataFrame({
        'open': data['Open'],
        'high': data['High'],
        'low': data['Low'],
        'close': data['Close'],
        'volume': data['Volume']
    })
    
    engineer = FeatureEngineer()
    features = engineer.calculate_price_features(df)
    
    for feature, value in features.items():
        print(f"{feature}: {value:.4f}")
