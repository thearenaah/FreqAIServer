"""
Candle Pattern Recognition
Identifies bullish and bearish patterns for trade confirmation
"""
import numpy as np
from typing import Dict, Optional


class CandlePatterns:
    """Recognize candle patterns for entry confirmation"""
    
    @staticmethod
    def calculate_candle_body_and_wicks(
        open_price: float,
        high: float,
        low: float,
        close: float
    ) -> Dict[str, float]:
        """Calculate candle metrics"""
        body_size = abs(close - open_price)
        upper_wick = high - max(open_price, close)
        lower_wick = min(open_price, close) - low
        total_range = high - low
        
        # Normalize to percentage of total range
        body_pct = body_size / total_range if total_range > 0 else 0
        upper_wick_pct = upper_wick / total_range if total_range > 0 else 0
        lower_wick_pct = lower_wick / total_range if total_range > 0 else 0
        
        return {
            'body_size': body_size,
            'upper_wick': upper_wick,
            'lower_wick': lower_wick,
            'total_range': total_range,
            'body_pct': body_pct,
            'upper_wick_pct': upper_wick_pct,
            'lower_wick_pct': lower_wick_pct,
            'is_bullish': close > open_price,
            'is_bearish': close < open_price,
        }
    
    @staticmethod
    def pin_bar(
        open_price: float,
        high: float,
        low: float,
        close: float,
        wick_threshold: float = 2.0
    ) -> Dict:
        """
        Pin Bar (Hammer/Hanging Man)
        
        One small body with a long wick on one side
        Indicates potential reversal
        
        Long wick should be 2x+ the body
        """
        metrics = CandlePatterns.calculate_candle_body_and_wicks(open_price, high, low, close)
        
        is_pin_bar = False
        pattern_type = None
        strength = 0
        
        if metrics['total_range'] > 0:
            # Hammer: Long lower wick, bullish close, small upper wick
            if (metrics['lower_wick'] > metrics['body_size'] * wick_threshold and
                metrics['upper_wick_pct'] < 0.1 and
                metrics['is_bullish']):
                is_pin_bar = True
                pattern_type = 'hammer'
                strength = min(metrics['lower_wick'] / metrics['body_size'] / wick_threshold, 1.0)
            
            # Hanging Man: Long lower wick, bearish close, small upper wick
            elif (metrics['lower_wick'] > metrics['body_size'] * wick_threshold and
                  metrics['upper_wick_pct'] < 0.1 and
                  metrics['is_bearish']):
                is_pin_bar = True
                pattern_type = 'hanging_man'
                strength = min(metrics['lower_wick'] / metrics['body_size'] / wick_threshold, 1.0)
            
            # Inverted Hammer: Long upper wick, bullish close
            elif (metrics['upper_wick'] > metrics['body_size'] * wick_threshold and
                  metrics['lower_wick_pct'] < 0.1 and
                  metrics['is_bullish']):
                is_pin_bar = True
                pattern_type = 'inverted_hammer'
                strength = min(metrics['upper_wick'] / metrics['body_size'] / wick_threshold, 1.0)
            
            # Shooting Star: Long upper wick, bearish close
            elif (metrics['upper_wick'] > metrics['body_size'] * wick_threshold and
                  metrics['lower_wick_pct'] < 0.1 and
                  metrics['is_bearish']):
                is_pin_bar = True
                pattern_type = 'shooting_star'
                strength = min(metrics['upper_wick'] / metrics['body_size'] / wick_threshold, 1.0)
        
        return {
            'is_pin_bar': is_pin_bar,
            'type': pattern_type,
            'strength': strength,  # 0-1
        }
    
    @staticmethod
    def engulfing(
        prev_open: float,
        prev_high: float,
        prev_low: float,
        prev_close: float,
        open_price: float,
        high: float,
        low: float,
        close: float,
    ) -> Dict:
        """
        Engulfing Pattern
        Current candle body completely engulfs previous candle
        
        Bullish: White candle engulfs black candle
        Bearish: Black candle engulfs white candle
        """
        prev_metrics = CandlePatterns.calculate_candle_body_and_wicks(
            prev_open, prev_high, prev_low, prev_close
        )
        curr_metrics = CandlePatterns.calculate_candle_body_and_wicks(
            open_price, high, low, close
        )
        
        is_bullish_engulf = (
            prev_metrics['is_bearish'] and
            curr_metrics['is_bullish'] and
            open_price <= prev_close and
            close >= prev_open and
            curr_metrics['body_size'] > prev_metrics['body_size']
        )
        
        is_bearish_engulf = (
            prev_metrics['is_bullish'] and
            curr_metrics['is_bearish'] and
            open_price >= prev_close and
            close <= prev_open and
            curr_metrics['body_size'] > prev_metrics['body_size']
        )
        
        return {
            'is_engulfing': is_bullish_engulf or is_bearish_engulf,
            'type': 'bullish_engulfing' if is_bullish_engulf else (
                'bearish_engulfing' if is_bearish_engulf else None
            ),
            'strength': curr_metrics['body_pct'],  # Larger body = stronger
        }
    
    @staticmethod
    def outside_bar(
        prev_high: float,
        prev_low: float,
        high: float,
        low: float,
    ) -> Dict:
        """
        Outside Bar (Breakout)
        Current bar breaks both high and low of previous bar
        """
        is_outside = (high > prev_high and low < prev_low)
        
        return {
            'is_outside_bar': is_outside,
            'type': 'outside_bar' if is_outside else None,
        }
    
    @staticmethod
    def doji(
        open_price: float,
        high: float,
        low: float,
        close: float,
        body_threshold: float = 0.01
    ) -> Dict:
        """
        Doji Pattern
        Open and close are very close (indecision)
        """
        metrics = CandlePatterns.calculate_candle_body_and_wicks(
            open_price, high, low, close
        )
        
        is_doji = metrics['body_pct'] <= body_threshold
        
        # Doji with long wicks (indecision at levels)
        is_dragonfly = is_doji and metrics['lower_wick_pct'] > 0.3
        is_gravestone = is_doji and metrics['upper_wick_pct'] > 0.3
        
        return {
            'is_doji': is_doji,
            'type': 'doji',
            'subtype': (
                'dragonfly' if is_dragonfly else
                'gravestone' if is_gravestone else
                'neutral'
            ),
        }
    
    @staticmethod
    def detect_patterns(
        open_price: float,
        high: float,
        low: float,
        close: float,
        prev_open: Optional[float] = None,
        prev_high: Optional[float] = None,
        prev_low: Optional[float] = None,
        prev_close: Optional[float] = None,
    ) -> Dict:
        """
        Detect all patterns in current candle
        Returns patterns with confidence levels
        """
        patterns = {
            'pin_bar': CandlePatterns.pin_bar(open_price, high, low, close),
            'outside_bar': CandlePatterns.outside_bar(prev_high, prev_low, high, low) if prev_high else None,
            'doji': CandlePatterns.doji(open_price, high, low, close),
        }
        
        if prev_open is not None:
            patterns['engulfing'] = CandlePatterns.engulfing(
                prev_open, prev_high, prev_low, prev_close,
                open_price, high, low, close
            )
        
        return patterns


if __name__ == "__main__":
    # Example: Hammer pattern
    print("=== Hammer Pattern ===")
    hammer = CandlePatterns.pin_bar(
        open_price=1.2050,
        high=1.2100,
        low=1.1950,  # Long lower wick
        close=1.2095  # Bullish close
    )
    print(f"Is Pin Bar: {hammer['is_pin_bar']}")
    print(f"Type: {hammer['type']}")
    print(f"Strength: {hammer['strength']:.2f}")
    
    # Example: Engulfing
    print("\n=== Bullish Engulfing ===")
    engulf = CandlePatterns.engulfing(
        prev_open=1.2100,
        prev_high=1.2120,
        prev_low=1.2050,
        prev_close=1.2055,
        open_price=1.2050,
        high=1.2150,
        low=1.2000,
        close=1.2140,
    )
    print(f"Is Engulfing: {engulf['is_engulfing']}")
    print(f"Type: {engulf['type']}")
    print(f"Strength: {engulf['strength']:.2f}")
