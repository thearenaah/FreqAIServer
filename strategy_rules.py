"""
Trading Strategy Rules Engine
Defines the exact logic for LONG and SHORT signals
Based on EMA, Pivot Points, Fibonacci Levels, RSI, and Candle Patterns
Includes TP/SL calculation via risk management
"""
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum
from fibonacci_levels import FibonacciLevels
from risk_management import RiskManagement, RiskManagementConfig


class Signal(Enum):
    LONG = "buy"
    SHORT = "sell"
    HOLD = "hold"


@dataclass
class StrategyRules:
    """Configuration for the trading strategy"""
    
    # EMA Settings
    ema_fast: int = 50          # Fast EMA for support/resistance
    ema_slow: int = 200         # Slow EMA for trend confirmation
    
    # RSI Settings
    rsi_period: int = 14
    rsi_overbought: float = 70  # But not too strict
    rsi_oversold: float = 30    # But not too strict
    
    # Pivot Point Settings
    use_camarilla: bool = False  # Floor (False) or Camarilla (True)
    pivot_tolerance: float = 0.003  # 0.3% - How close to pivot counts as "at level"
    
    # Fibonacci Settings
    use_fibonacci: bool = True  # Enable Fibonacci levels
    fibonacci_tolerance: float = 0.003  # 0.3% - How close to Fib level counts
    fibonacci_min_strength: float = 0.4  # Minimum confidence for Fib level
    
    # Candle Pattern Settings
    require_pattern_confirmation: bool = True
    min_pattern_strength: float = 0.5  # 0-1
    
    # Price Action Settings
    breakout_threshold: float = 0.001  # 0.1% - How much beyond level counts as break
    retest_threshold: float = 0.0005   # 0.05% - Tolerance for retest
    
    # Risk Management
    require_ema_alignment: bool = True  # Price should align with EMA trend
    max_candles_from_level: int = 3    # How many candles to look back for level break
    
    # TP/SL Configuration
    calculate_tp_sl: bool = True       # Calculate TP/SL for each signal
    tp1_risk_reward: float = 1.0       # TP1: 1:1 ratio
    tp2_risk_reward: float = 2.0       # TP2: 2:1 ratio
    tp3_risk_reward: float = 3.0       # TP3: 3:1 ratio


class StrategyEngine:
    """Execute strategy rules and generate signals"""
    
    def __init__(self, rules: StrategyRules = None):
        self.rules = rules or StrategyRules()
        # Initialize risk management with config based on strategy rules
        rm_config = RiskManagementConfig(
            tp1_risk_reward=rules.tp1_risk_reward,
            tp2_risk_reward=rules.tp2_risk_reward,
            tp3_risk_reward=rules.tp3_risk_reward,
        )
        self.risk_manager = RiskManagement(rm_config)
    
    def check_long_signal(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        rsi: float,
        pivot_data: Dict[str, float],
        candle_patterns: Dict = None,
        recent_price_action: Dict = None,
    ) -> tuple:
        """
        Generate LONG signal
        
        Rules:
        1. Price near support (EMA 50/200 or pivot level)
        2. Price bounces from support (candle pattern confirmation)
        3. RSI not in extreme oversold (allows recovery)
        4. EMA 50 above EMA 200 (uptrend) OR price testing support
        5. Pattern confirmation (hammer, bullish engulfing, etc.)
        """
        signal = Signal.HOLD
        confidence = 0.0
        reasons = []
        
        # Rule 1: Check EMA alignment
        ema_aligned = ema_50 > ema_200
        if ema_aligned:
            reasons.append("EMA 50 > EMA 200 (uptrend)")
            confidence += 0.15
        
        # Rule 2: Price near support levels
        support_strength = self._find_support_strength(
            price, ema_50, ema_200, pivot_data
        )
        
        if support_strength > 0:
            reasons.append(f"Price near support (strength: {support_strength:.2f})")
            confidence += support_strength * 0.20
        
        # Rule 3: RSI not too cold (allow recovery from oversold)
        if rsi < self.rules.rsi_overbought:
            reasons.append(f"RSI favorable ({rsi:.1f})")
            if rsi < self.rules.rsi_oversold:
                confidence += 0.15  # Extra confidence if oversold
            else:
                confidence += 0.05
        
        # Rule 4: Candle pattern confirmation
        pattern_strength = self._evaluate_bullish_patterns(candle_patterns)
        if pattern_strength > self.rules.min_pattern_strength:
            reasons.append(f"Bullish pattern confirmed (strength: {pattern_strength:.2f})")
            confidence += pattern_strength * 0.25
        elif self.rules.require_pattern_confirmation:
            confidence -= 0.15  # Reduce confidence if pattern required but missing
        
        # Rule 5: Price action (recent bounce from support)
        if recent_price_action:
            bounce_quality = self._check_price_action_bounce(
                recent_price_action, ema_50
            )
            if bounce_quality > 0:
                reasons.append(f"Price action bounce confirmed ({bounce_quality:.2f})")
                confidence += bounce_quality * 0.20
        
        # Final decision
        if confidence >= 0.50:  # At least 50% confidence
            signal = Signal.LONG
        
        return signal, confidence, reasons
    
    def check_short_signal(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        rsi: float,
        pivot_data: Dict[str, float],
        candle_patterns: Dict = None,
        recent_price_action: Dict = None,
    ) -> tuple:
        """
        Generate SHORT signal
        
        Rules (opposite of LONG):
        1. Price near resistance (EMA 50/200 or pivot level)
        2. Price rejected from resistance (candle pattern)
        3. RSI not in extreme overbought (allows pullback)
        4. EMA 50 below EMA 200 (downtrend) OR price testing resistance
        5. Pattern confirmation (shooting star, bearish engulfing, etc.)
        """
        signal = Signal.HOLD
        confidence = 0.0
        reasons = []
        
        # Rule 1: Check EMA alignment
        ema_aligned = ema_50 < ema_200
        if ema_aligned:
            reasons.append("EMA 50 < EMA 200 (downtrend)")
            confidence += 0.15
        
        # Rule 2: Price near resistance levels
        resistance_strength = self._find_resistance_strength(
            price, ema_50, ema_200, pivot_data
        )
        
        if resistance_strength > 0:
            reasons.append(f"Price near resistance (strength: {resistance_strength:.2f})")
            confidence += resistance_strength * 0.20
        
        # Rule 3: RSI not too hot (allow pullback from overbought)
        if rsi > self.rules.rsi_oversold:
            reasons.append(f"RSI favorable ({rsi:.1f})")
            if rsi > self.rules.rsi_overbought:
                confidence += 0.15  # Extra confidence if overbought
            else:
                confidence += 0.05
        
        # Rule 4: Candle pattern confirmation
        pattern_strength = self._evaluate_bearish_patterns(candle_patterns)
        if pattern_strength > self.rules.min_pattern_strength:
            reasons.append(f"Bearish pattern confirmed (strength: {pattern_strength:.2f})")
            confidence += pattern_strength * 0.25
        elif self.rules.require_pattern_confirmation:
            confidence -= 0.15
        
        # Rule 5: Price action (recent rejection from resistance)
        if recent_price_action:
            rejection_quality = self._check_price_action_rejection(
                recent_price_action, ema_50
            )
            if rejection_quality > 0:
                reasons.append(f"Price action rejection confirmed ({rejection_quality:.2f})")
                confidence += rejection_quality * 0.20
        
        # Final decision
        if confidence >= 0.50:
            signal = Signal.SHORT
        
        return signal, confidence, reasons
    
    def _find_support_strength(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        pivot_data: Dict[str, float],
        fibonacci_data: Dict = None
    ) -> float:
        """
        Check how strong the support is
        Considers: EMAs, pivot points, and Fibonacci levels
        Returns 0-1 confidence
        """
        support_levels = []
        
        # EMA 50 as support
        if abs(price - ema_50) / price < self.rules.pivot_tolerance:
            support_levels.append(('ema_50', 0.60))
        
        # EMA 200 as support
        if abs(price - ema_200) / price < self.rules.pivot_tolerance:
            support_levels.append(('ema_200', 0.70))
        
        # Pivot support levels
        for level_name in ['s1', 's2', 's3']:
            if level_name in pivot_data:
                if abs(price - pivot_data[level_name]) / price < self.rules.pivot_tolerance:
                    strength = 0.50 if level_name == 's1' else 0.65
                    support_levels.append((level_name, strength))
        
        # Fibonacci support levels
        if self.rules.use_fibonacci and fibonacci_data:
            fib_support = self._evaluate_fibonacci_support(price, fibonacci_data)
            if fib_support > 0:
                support_levels.append(('fibonacci', fib_support))
        
        # Return highest strength (best support)
        if support_levels:
            return max([strength for _, strength in support_levels])
        return 0.0
    
    def _find_resistance_strength(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        pivot_data: Dict[str, float],
        fibonacci_data: Dict = None
    ) -> float:
        """
        Check how strong the resistance is
        Considers: EMAs, pivot points, and Fibonacci levels
        Returns 0-1 confidence
        """
        resistance_levels = []
        
        # EMA 50 as resistance
        if abs(price - ema_50) / price < self.rules.pivot_tolerance:
            resistance_levels.append(('ema_50', 0.60))
        
        # EMA 200 as resistance
        if abs(price - ema_200) / price < self.rules.pivot_tolerance:
            resistance_levels.append(('ema_200', 0.70))
        
        # Pivot resistance levels
        for level_name in ['r1', 'r2', 'r3']:
            if level_name in pivot_data:
                if abs(price - pivot_data[level_name]) / price < self.rules.pivot_tolerance:
                    strength = 0.50 if level_name == 'r1' else 0.65
                    resistance_levels.append((level_name, strength))
        
        # Fibonacci resistance levels
        if self.rules.use_fibonacci and fibonacci_data:
            fib_resistance = self._evaluate_fibonacci_resistance(price, fibonacci_data)
            if fib_resistance > 0:
                resistance_levels.append(('fibonacci', fib_resistance))
        
        # Return highest strength (best resistance)
        if resistance_levels:
            return max([strength for _, strength in resistance_levels])
        return 0.0
    
    def _evaluate_bullish_patterns(self, patterns: Dict = None) -> float:
        """Evaluate bullish candle patterns"""
        if not patterns:
            return 0.0
        
        strength = 0.0
        
        # Hammer is bullish
        if patterns.get('pin_bar', {}).get('type') == 'hammer':
            strength = max(strength, patterns['pin_bar']['strength'])
        
        # Bullish engulfing
        if patterns.get('engulfing', {}).get('type') == 'bullish_engulfing':
            strength = max(strength, patterns['engulfing']['strength'])
        
        # Inverted hammer (rejection of high)
        if patterns.get('pin_bar', {}).get('type') == 'inverted_hammer':
            strength = max(strength, patterns['pin_bar']['strength'] * 0.7)
        
        return min(strength, 1.0)
    
    def _evaluate_bearish_patterns(self, patterns: Dict = None) -> float:
        """Evaluate bearish candle patterns"""
        if not patterns:
            return 0.0
        
        strength = 0.0
        
        # Shooting star is bearish
        if patterns.get('pin_bar', {}).get('type') == 'shooting_star':
            strength = max(strength, patterns['pin_bar']['strength'])
        
        # Bearish engulfing
        if patterns.get('engulfing', {}).get('type') == 'bearish_engulfing':
            strength = max(strength, patterns['engulfing']['strength'])
        
        # Hanging man (rejection of low)
        if patterns.get('pin_bar', {}).get('type') == 'hanging_man':
            strength = max(strength, patterns['pin_bar']['strength'] * 0.7)
        
        return min(strength, 1.0)
    
    def _check_price_action_bounce(
        self,
        recent_action: Dict,
        ema_50: float
    ) -> float:
        """Check if price is bouncing from support"""
        if not recent_action or 'lowest_price' not in recent_action:
            return 0.0
        
        lowest = recent_action['lowest_price']
        current = recent_action['current_price']
        highest = recent_action['highest_price']
        
        # Check if there's a bounce
        bounce_distance = current - lowest
        total_range = highest - lowest
        
        if total_range > 0 and bounce_distance / total_range > 0.3:
            # Good bounce
            return min(bounce_distance / total_range, 1.0)
        
        return 0.0
    
    def _check_price_action_rejection(
        self,
        recent_action: Dict,
        ema_50: float
    ) -> float:
        """Check if price is rejecting from resistance"""
        if not recent_action or 'highest_price' not in recent_action:
            return 0.0
        
        highest = recent_action['highest_price']
        current = recent_action['current_price']
        lowest = recent_action['lowest_price']
        
        # Check if there's a rejection
        rejection_distance = highest - current
        total_range = highest - lowest
        
        if total_range > 0 and rejection_distance / total_range > 0.3:
            # Good rejection
            return min(rejection_distance / total_range, 1.0)
        
        return 0.0
    
    def _evaluate_fibonacci_support(
        self,
        price: float,
        fibonacci_data: Dict
    ) -> float:
        """
        Evaluate Fibonacci support levels
        Returns 0-1 confidence based on proximity to Fibonacci retracement level
        
        Stronger Fibonacci levels: 38.2%, 50%, 61.8% (Golden Ratio)
        Weaker levels: 23.6%, 78.6%
        """
        if not fibonacci_data or 'all_levels' not in fibonacci_data:
            return 0.0
        
        levels = fibonacci_data['all_levels']
        
        # Strong Fibonacci levels have higher confidence
        strong_levels = {
            '38.2%': 0.65,
            '50.0%': 0.70,
            '61.8%': 0.75,  # Golden Ratio - strongest
        }
        
        for level_name, level_strength in strong_levels.items():
            if level_name in levels:
                level_data = levels[level_name]
                distance = abs(price - level_data.level) / price
                
                if distance <= self.rules.fibonacci_tolerance:
                    # Closer to level = higher confidence
                    confidence = level_strength * max(0.0, 1.0 - (distance / self.rules.fibonacci_tolerance))
                    if confidence >= self.rules.fibonacci_min_strength:
                        return confidence
        
        return 0.0
    
    def _evaluate_fibonacci_resistance(
        self,
        price: float,
        fibonacci_data: Dict
    ) -> float:
        """
        Evaluate Fibonacci resistance levels
        Same as support but for resistance (price bouncing up)
        """
        return self._evaluate_fibonacci_support(price, fibonacci_data)
    
    def evaluate_fibonacci_confluence(
        self,
        price: float,
        fibonacci_data: Dict,
        pivot_data: Dict,
        ema_50: float,
        ema_200: float
    ) -> Dict:
        """
        Evaluate Fibonacci and Pivot Point confluence
        Multiple confluence = stronger signal
        
        Returns dictionary with:
        - confluence_level: 0-1 confidence
        - touching_levels: List of levels price is near
        - confluence_reason: Human-readable explanation
        """
        confluence_count = 0
        touching_levels = []
        
        # Check Fibonacci levels
        if fibonacci_data and 'all_levels' in fibonacci_data:
            fib_levels = fibonacci_data['all_levels']
            for level_name, level_data in fib_levels.items():
                distance = abs(price - level_data.level) / price
                if distance <= self.rules.fibonacci_tolerance:
                    touching_levels.append(f"Fibonacci {level_name} ({level_data.level:.2f})")
                    confluence_count += 1
        
        # Check Pivot levels
        if pivot_data:
            for level_name in ['r1', 'r2', 'r3', 's1', 's2', 's3']:
                if level_name in pivot_data:
                    distance = abs(price - pivot_data[level_name]) / price
                    if distance <= self.rules.pivot_tolerance:
                        touching_levels.append(f"Pivot {level_name.upper()} ({pivot_data[level_name]:.2f})")
                        confluence_count += 1
        
        # Check EMA levels
        if abs(price - ema_50) / price <= self.rules.fibonacci_tolerance:
            touching_levels.append(f"EMA 50 ({ema_50:.2f})")
            confluence_count += 1
        
        if abs(price - ema_200) / price <= self.rules.fibonacci_tolerance:
            touching_levels.append(f"EMA 200 ({ema_200:.2f})")
            confluence_count += 1
        
        # Calculate confluence confidence
        # 1 level = weak, 2 levels = fair, 3+ levels = strong
        confluence_confidence = min(confluence_count / 3.0, 1.0)  # Max 1.0
        
        reason = ""
        if confluence_count == 0:
            reason = "No confluence - price away from all key levels"
        elif confluence_count == 1:
            reason = f"Weak confluence - at {touching_levels[0]}"
        elif confluence_count == 2:
            reason = f"Fair confluence - at {', '.join(touching_levels)}"
        else:
            reason = f"Strong confluence - at {', '.join(touching_levels)}"
        
        return {
            'confluence_level': confluence_confidence,
            'confluence_count': confluence_count,
            'touching_levels': touching_levels,
            'confluence_reason': reason
        }
    
    # ========== TP/SL CALCULATION METHODS ==========
    
    def calculate_long_tp_sl(
        self,
        entry_price: float,
        support_level: float,
        pivot_data: Dict[str, float] = None,
        fibonacci_data: Dict[str, float] = None,
        atr: float = None,
        highest_recent: float = None,
    ) -> Dict:
        """
        Calculate TP and SL levels for LONG trades
        
        SL Rules:
        - Place SL below support level
        - Consider ATR for volatility adjustment
        - Minimum SL offset of 0.5% below support
        
        TP Rules:
        - TP1: 1:1 risk/reward (nearest pivot R1 or Fib level)
        - TP2: 2:1 risk/reward (next pivot R2 or Fib extension)
        - TP3: 3:1 risk/reward (strong pivot R3 or max profit target)
        
        Returns complete trade setup with entry, SL, TP1/TP2/TP3
        """
        if not self.rules.calculate_tp_sl:
            return {'error': 'TP/SL calculation disabled'}
        
        trade_setup = self.risk_manager.calculate_long_trade_levels(
            entry_price=entry_price,
            support_level=support_level,
            pivot_data=pivot_data,
            fibonacci_data=fibonacci_data,
            atr=atr,
            highest_recent_price=highest_recent,
        )
        
        # Validate trade setup
        validation = self.risk_manager.validate_trade_setup(trade_setup)
        trade_setup['validation'] = validation
        
        return trade_setup
    
    def calculate_short_tp_sl(
        self,
        entry_price: float,
        resistance_level: float,
        pivot_data: Dict[str, float] = None,
        fibonacci_data: Dict[str, float] = None,
        atr: float = None,
        lowest_recent: float = None,
    ) -> Dict:
        """
        Calculate TP and SL levels for SHORT trades
        
        SL Rules:
        - Place SL above resistance level
        - Consider ATR for volatility adjustment
        - Minimum SL offset of 0.5% above resistance
        
        TP Rules:
        - TP1: 1:1 risk/reward (nearest pivot S1 or Fib retracement)
        - TP2: 2:1 risk/reward (next pivot S2)
        - TP3: 3:1 risk/reward (strong pivot S3 or max profit target)
        
        Returns complete trade setup with entry, SL, TP1/TP2/TP3
        """
        if not self.rules.calculate_tp_sl:
            return {'error': 'TP/SL calculation disabled'}
        
        trade_setup = self.risk_manager.calculate_short_trade_levels(
            entry_price=entry_price,
            resistance_level=resistance_level,
            pivot_data=pivot_data,
            fibonacci_data=fibonacci_data,
            atr=atr,
            lowest_recent_price=lowest_recent,
        )
        
        # Validate trade setup
        validation = self.risk_manager.validate_trade_setup(trade_setup)
        trade_setup['validation'] = validation
        
        return trade_setup
    
    def get_trade_summary(self, trade_setup: Dict) -> str:
        """
        Get human-readable trade summary from trade setup
        
        Example:
        LONG: Entry 1.2050 | SL 1.2030 (Risk: 0.002) | 
        TP1 1.2070 (1:1) | TP2 1.2090 (2:1) | TP3 1.2110 (3:1) |
        RR: 2.5:1 | Valid: ✓
        """
        if 'error' in trade_setup:
            return f"Error: {trade_setup['error']}"
        
        summary = trade_setup.get('trade_description', 'No trade description')
        
        validation = trade_setup.get('validation', {})
        if validation.get('is_valid'):
            summary += " | ✓ VALID"
        else:
            summary += " | ✗ INVALID"
            if validation.get('errors'):
                summary += f" - {validation['errors'][0]}"
        
        return summary


if __name__ == "__main__":
    # Example usage
    rules = StrategyRules()
    engine = StrategyEngine(rules)
    
    # Simulated market data
    pivot_data = {
        's2': 1.2000,
        's1': 1.2025,
        'pivot': 1.2050,
        'r1': 1.2075,
        'r2': 1.2100,
    }
    
    candle_patterns = {
        'pin_bar': {'type': 'hammer', 'strength': 0.8},
        'engulfing': {'type': None},
    }
    
    # Test LONG signal
    signal, confidence, reasons = engine.check_long_signal(
        price=1.2030,
        ema_50=1.2020,
        ema_200=1.2000,
        rsi=35,
        pivot_data=pivot_data,
        candle_patterns=candle_patterns,
    )
    
    print(f"Signal: {signal.value}")
    print(f"Confidence: {confidence:.2f}")
    print("Reasons:")
    for reason in reasons:
        print(f"  - {reason}")
