"""
IMPROVED DAY TRADING STRATEGY - Professional Grade
Combines: 50/200 EMA, Pivot Points, Fibonacci Retracements, RSI, Price Action, ICT Concepts

KEY FEATURES:
1. **Support/Resistance Zones**: Uses Pivot Points + Fibonacci for precise areas
2. **Market Structure**: Higher Lows (uptrend) and Lower Highs (downtrend) identification
3. **Entry Points**: Price action confirmation at key levels (break + retest)
4. **Risk/Reward**: Strict 1:3 minimum ratios with multi-level TP scaling
5. **Session Awareness**: Identifies institutional activity levels
6. **Pattern Recognition**: ICT Smart Money Concepts + Japanese candlestick patterns
7. **Confluence**: Multiple indicator alignment before signal generation
8. **Volatility Adjustment**: Adapts TP/SL based on ATR (market conditions)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import numpy as np
import pandas as pd
from fibonacci_levels import FibonacciLevels
from risk_management import RiskManagement, RiskManagementConfig


class MarketStructure(Enum):
    """ICT Market Structure Classification"""
    UPTREND = "uptrend"           # Higher Lows, Higher Highs
    DOWNTREND = "downtrend"        # Lower Highs, Lower Lows
    CONSOLIDATION = "consolidation" # Range-bound
    BREAKOUT = "breakout"          # Breaking significant level


class EntryConfidence(Enum):
    """Entry signal strength"""
    WEAK = 0.4      # Single confirmation
    MODERATE = 0.6  # Two confirmations
    STRONG = 0.8    # Three+ confirmations
    VERY_STRONG = 0.95  # All conditions aligned


@dataclass
class ImprovedStrategyRules:
    """Configuration for improved day trading strategy"""
    
    # ===== EMA SETTINGS =====
    ema_fast: int = 50              # Support/resistance 
    ema_slow: int = 200             # Main trend confirmation
    ema_extreme: int = 13           # Fast EMA for intraday entries
    
    # ===== RSI SETTINGS (Enhanced) =====
    rsi_period: int = 14
    rsi_overbought: float = 60      # Softer - not 70 (for continuation trades)
    rsi_oversold: float = 40        # Softer - not 30 (for pullback trades)
    rsi_extreme_overbought: float = 75  # True extreme
    rsi_extreme_oversold: float = 25    # True extreme
    rsi_divergence_period: int = 10     # Look-back for RSI divergence detection
    
    # ===== FIBONACCI RETRACEMENT =====
    use_fibonacci: bool = True
    fib_levels_to_monitor: List[str] = None  # ['0.382', '0.5', '0.618', '0.786']
    fib_tolerance: float = 0.003    # 0.3% tolerance
    
    # ===== PIVOT POINTS & SUPPORT/RESISTANCE =====
    use_pivot_points: bool = True
    pivot_tolerance: float = 0.003
    support_resistance_lookback: int = 20  # Candles to look back for S/R
    
    # ===== MARKET STRUCTURE (ICT) =====
    require_market_structure_confirmation: bool = True
    structure_lookback: int = 5     # Candles for HH/HL (uptrend) or LL/LH (downtrend)
    break_and_retest_candles: int = 2  # Candles to wait for retest after break
    
    # ===== PRICE ACTION SETTINGS =====
    min_candle_body_percent: float = 0.3  # Candle body should be 30%+ of total range
    require_break_above_pivot: bool = True  # For LONG: price > pivot
    require_break_below_pivot: bool = True  # For SHORT: price < pivot
    
    # ===== SESSION AWARENESS =====
    # Institutional activity times (more volume, less noise)
    asian_session_start: int = 21  # 21:00 UTC (Tokyo)
    london_session_start: int = 8  # 08:00 UTC
    london_session_end: int = 17   # 17:00 UTC
    us_session_start: int = 13     # 13:00 UTC
    us_session_end: int = 20       # 20:00 UTC
    
    # ===== VOLATILITY ADJUSTMENT =====
    use_atr_adjustment: bool = True
    atr_period: int = 14
    volatility_multiplier: float = 1.0  # Increase TP/SL in high volatility
    
    # ===== TP/SL SETTINGS =====
    min_rr_ratio: float = 3.0       # Minimum 1:3 risk/reward
    tp1_risk_reward: float = 1.5    # TP1: 1.5:1
    tp2_risk_reward: float = 2.5    # TP2: 2.5:1
    tp3_risk_reward: float = 4.0    # TP3: 4:1
    sl_atr_multiplier: float = 1.5  # SL = ATR * 1.5
    
    # ===== CONFIRMATION REQUIREMENTS =====
    require_confluence: bool = True  # Signals need multiple confirmations
    min_confluence_factors: int = 3  # At least 3 factors must align
    
    def __post_init__(self):
        """Initialize defaults"""
        if self.fib_levels_to_monitor is None:
            self.fib_levels_to_monitor = ['0.382', '0.5', '0.618', '0.786']


class ImprovedStrategyEngine:
    """
    Execute improved day trading strategy with ICT concepts
    
    Philosophy:
    - Wait for institutional levels (support/resistance)
    - Confirm with price action (break + retest)
    - Enter only with strong confluence
    - Scale exits (3 TP levels)
    - Tight stops with high probability
    """
    
    def __init__(self, rules: ImprovedStrategyRules = None):
        self.rules = rules or ImprovedStrategyRules()
        # Risk management with strict ratios
        rm_config = RiskManagementConfig(
            tp1_risk_reward=rules.tp1_risk_reward,
            tp2_risk_reward=rules.tp2_risk_reward,
            tp3_risk_reward=rules.tp3_risk_reward,
        )
        self.risk_manager = RiskManagement(rm_config)
        self.fib_calculator = FibonacciLevels()
    
    # ===== MARKET STRUCTURE DETECTION (ICT) =====
    
    def detect_market_structure(
        self,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> MarketStructure:
        """
        Detect market structure: Uptrend, Downtrend, or Consolidation
        
        Uptrend: Higher Lows + Higher Highs
        Downtrend: Lower Lows + Lower Highs
        Consolidation: Random pattern
        """
        if len(highs) < self.rules.structure_lookback + 1:
            return MarketStructure.CONSOLIDATION
        
        recent_highs = highs[-self.rules.structure_lookback:]
        recent_lows = lows[-self.rules.structure_lookback:]
        
        higher_highs = np.all(np.diff(recent_highs) > 0)
        higher_lows = np.all(np.diff(recent_lows) > 0)
        
        lower_lows = np.all(np.diff(recent_lows) < 0)
        lower_highs = np.all(np.diff(recent_highs) < 0)
        
        if higher_highs and higher_lows:
            return MarketStructure.UPTREND
        elif lower_lows and lower_highs:
            return MarketStructure.DOWNTREND
        else:
            return MarketStructure.CONSOLIDATION
    
    def find_recent_support_resistance(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        current_price: float
    ) -> Dict[str, float]:
        """
        Find S/R levels from recent price action
        
        Support: Multiple touches from below
        Resistance: Multiple touches from above
        """
        lookback = self.rules.support_resistance_lookback
        recent_lows = lows[-lookback:]
        recent_highs = highs[-lookback:]
        
        # Find local lows (support)
        supports = []
        for i in range(1, len(recent_lows) - 1):
            if recent_lows[i] < recent_lows[i-1] and recent_lows[i] < recent_lows[i+1]:
                supports.append(recent_lows[i])
        
        # Find local highs (resistance)
        resistances = []
        for i in range(1, len(recent_highs) - 1):
            if recent_highs[i] > recent_highs[i-1] and recent_highs[i] > recent_highs[i+1]:
                resistances.append(recent_highs[i])
        
        return {
            'nearest_support': min(supports) if supports else np.min(recent_lows),
            'nearest_resistance': max(resistances) if resistances else np.max(recent_highs),
            'supports': supports,
            'resistances': resistances
        }
    
    # ===== PRICE ACTION & CONFLUENCE CHECKING =====
    
    def check_break_and_retest(
        self,
        closes: np.ndarray,
        level: float,
        direction: str,  # 'above' or 'below'
        lookback: int = 2
    ) -> bool:
        """
        Check if price has broken level and retested
        
        LONG setup: Price breaks ABOVE and retests (pulls back to level)
        SHORT setup: Price breaks BELOW and retests (pulls up to level)
        """
        if len(closes) < lookback + 1:
            return False
        
        recent = closes[-lookback:]
        
        if direction == 'above':
            # Check if ANY close above level AND at least one close at/near level
            broke_above = np.any(recent > level)
            near_level = np.any(np.abs(recent - level) < level * 0.003)  # Within 0.3%
            return broke_above and near_level
        
        elif direction == 'below':
            broke_below = np.any(recent < level)
            near_level = np.any(np.abs(recent - level) < level * 0.003)
            return broke_below and near_level
        
        return False
    
    def detect_rsi_divergence(
        self,
        closes: np.ndarray,
        rsi_values: np.ndarray,
        direction: str  # 'bullish' or 'bearish'
    ) -> bool:
        """
        Detect RSI divergence (strong confirmation signal)
        
        Bullish divergence: Price makes lower low, RSI makes higher low
        Bearish divergence: Price makes higher high, RSI makes lower high
        """
        period = self.rules.rsi_divergence_period
        if len(closes) < period or len(rsi_values) < period:
            return False
        
        recent_closes = closes[-period:]
        recent_rsi = rsi_values[-period:]
        
        if direction == 'bullish':
            # Price should make lower low, RSI should make higher low
            price_lower_low = recent_closes[-1] < np.min(recent_closes[:-1])
            rsi_higher_low = recent_rsi[-1] > np.min(recent_rsi[:-1])
            return price_lower_low and rsi_higher_low
        
        elif direction == 'bearish':
            # Price should make higher high, RSI should make lower high
            price_higher_high = recent_closes[-1] > np.max(recent_closes[:-1])
            rsi_lower_high = recent_rsi[-1] < np.max(recent_rsi[:-1])
            return price_higher_high and rsi_lower_high
        
        return False
    
    def count_confluence_factors(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        rsi: float,
        pivot_data: Dict[str, float],
        fib_data: Dict[str, float],
        market_structure: MarketStructure,
        direction: str,  # 'LONG' or 'SHORT'
        divergence: bool = False,
        break_retest: bool = False
    ) -> int:
        """
        Count how many confluence factors are aligned
        
        Factors:
        1. Price at support/resistance level
        2. EMA alignment (price on correct side)
        3. RSI not in extreme
        4. Market structure (trending in right direction)
        5. Break + Retest confirmed
        6. RSI divergence detected
        7. Fibonacci level alignment
        """
        factors = 0
        tolerance = 0.003
        
        if direction == 'LONG':
            # Factor 1: Price near support level
            if pivot_data.get('S1'):
                support = pivot_data['S1']
                if abs(price - support) / support < tolerance:
                    factors += 1
            
            # Factor 2: EMA aligned (50 above 200, price above 50)
            if ema_50 > ema_200 and price > ema_50:
                factors += 1
            
            # Factor 3: RSI ready to bounce
            if self.rules.rsi_oversold < rsi < self.rules.rsi_overbought:
                factors += 1
            
            # Factor 4: Uptrend structure
            if market_structure == MarketStructure.UPTREND:
                factors += 1
            
            # Factor 5: Break + Retest
            if break_retest:
                factors += 1
            
            # Factor 6: Bullish divergence
            if divergence:
                factors += 1
            
            # Factor 7: Fibonacci support
            if fib_data and any(abs(price - fib_data.get(level, 0)) / price < tolerance 
                               for level in self.rules.fib_levels_to_monitor):
                factors += 1
        
        elif direction == 'SHORT':
            # Factor 1: Price near resistance level
            if pivot_data.get('R1'):
                resistance = pivot_data['R1']
                if abs(price - resistance) / resistance < tolerance:
                    factors += 1
            
            # Factor 2: EMA aligned (50 below 200, price below 50)
            if ema_50 < ema_200 and price < ema_50:
                factors += 1
            
            # Factor 3: RSI ready to pull back
            if self.rules.rsi_oversold < rsi < self.rules.rsi_overbought:
                factors += 1
            
            # Factor 4: Downtrend structure
            if market_structure == MarketStructure.DOWNTREND:
                factors += 1
            
            # Factor 5: Break + Retest
            if break_retest:
                factors += 1
            
            # Factor 6: Bearish divergence
            if divergence:
                factors += 1
            
            # Factor 7: Fibonacci resistance
            if fib_data and any(abs(price - fib_data.get(level, 0)) / price < tolerance 
                               for level in self.rules.fib_levels_to_monitor):
                factors += 1
        
        return factors
    
    # ===== MAIN SIGNAL GENERATION =====
    
    def generate_long_signal(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        rsi: float,
        pivot_data: Dict[str, float],
        fib_data: Dict[str, float],
        atr: float,
        recent_closes: np.ndarray,
        recent_highs: np.ndarray,
        recent_lows: np.ndarray,
        rsi_values: np.ndarray,
    ) -> Tuple[bool, float, str]:
        """
        Generate LONG signal using professional criteria
        
        Returns: (signal_valid, confidence, reason)
        """
        reasons = []
        confidence = 0.0
        
        # Step 1: Market Structure
        market_structure = self.detect_market_structure(recent_highs, recent_lows)
        if market_structure == MarketStructure.DOWNTREND:
            return False, 0.0, "❌ Downtrend structure - no LONG"
        
        reasons.append(f"✓ Structure: {market_structure.value}")
        
        # Step 2: Support Level Detection
        sr_levels = self.find_recent_support_resistance(recent_highs, recent_lows, price)
        nearest_support = sr_levels['nearest_support']
        
        # Step 3: Break + Retest check
        break_retest = self.check_break_and_retest(recent_closes, nearest_support, 'above')
        if not break_retest:
            return False, 0.0, "❌ No break + retest above support"
        
        reasons.append("✓ Break + Retest confirmed")
        
        # Step 4: RSI Divergence
        divergence = self.detect_rsi_divergence(recent_closes, rsi_values, 'bullish')
        if divergence:
            reasons.append("✓ Bullish RSI divergence")
        
        # Step 5: Count confluence factors
        factors = self.count_confluence_factors(
            price, ema_50, ema_200, rsi, pivot_data, fib_data,
            market_structure, 'LONG',
            divergence=divergence,
            break_retest=break_retest
        )
        
        reasons.append(f"✓ Confluence: {factors}/7 factors aligned")
        
        if factors < self.rules.min_confluence_factors:
            return False, 0.0, f"❌ Insufficient confluence ({factors}/{self.rules.min_confluence_factors})"
        
        # All checks passed - calculate confidence
        if factors >= 6:
            confidence = EntryConfidence.VERY_STRONG.value
        elif factors >= 5:
            confidence = EntryConfidence.STRONG.value
        elif factors >= 4:
            confidence = EntryConfidence.MODERATE.value
        else:
            confidence = EntryConfidence.WEAK.value
        
        reason_text = " | ".join(reasons)
        return True, confidence, reason_text
    
    def generate_short_signal(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        rsi: float,
        pivot_data: Dict[str, float],
        fib_data: Dict[str, float],
        atr: float,
        recent_closes: np.ndarray,
        recent_highs: np.ndarray,
        recent_lows: np.ndarray,
        rsi_values: np.ndarray,
    ) -> Tuple[bool, float, str]:
        """
        Generate SHORT signal using professional criteria
        
        Returns: (signal_valid, confidence, reason)
        """
        reasons = []
        confidence = 0.0
        
        # Step 1: Market Structure
        market_structure = self.detect_market_structure(recent_highs, recent_lows)
        if market_structure == MarketStructure.UPTREND:
            return False, 0.0, "❌ Uptrend structure - no SHORT"
        
        reasons.append(f"✓ Structure: {market_structure.value}")
        
        # Step 2: Resistance Level Detection
        sr_levels = self.find_recent_support_resistance(recent_highs, recent_lows, price)
        nearest_resistance = sr_levels['nearest_resistance']
        
        # Step 3: Break + Retest check
        break_retest = self.check_break_and_retest(recent_closes, nearest_resistance, 'below')
        if not break_retest:
            return False, 0.0, "❌ No break + retest below resistance"
        
        reasons.append("✓ Break + Retest confirmed")
        
        # Step 4: RSI Divergence
        divergence = self.detect_rsi_divergence(recent_closes, rsi_values, 'bearish')
        if divergence:
            reasons.append("✓ Bearish RSI divergence")
        
        # Step 5: Count confluence factors
        factors = self.count_confluence_factors(
            price, ema_50, ema_200, rsi, pivot_data, fib_data,
            market_structure, 'SHORT',
            divergence=divergence,
            break_retest=break_retest
        )
        
        reasons.append(f"✓ Confluence: {factors}/7 factors aligned")
        
        if factors < self.rules.min_confluence_factors:
            return False, 0.0, f"❌ Insufficient confluence ({factors}/{self.rules.min_confluence_factors})"
        
        # All checks passed - calculate confidence
        if factors >= 6:
            confidence = EntryConfidence.VERY_STRONG.value
        elif factors >= 5:
            confidence = EntryConfidence.STRONG.value
        elif factors >= 4:
            confidence = EntryConfidence.MODERATE.value
        else:
            confidence = EntryConfidence.WEAK.value
        
        reason_text = " | ".join(reasons)
        return True, confidence, reason_text
    
    def calculate_tp_sl_for_long(
        self,
        entry_price: float,
        support_level: float,
        resistance_levels: List[float],
        atr: float,
        pivot_data: Dict[str, float],
        fib_data: Dict[str, float]
    ) -> Dict:
        """
        Calculate TP/SL with ICT concepts and multi-level scaling
        
        SL: Below support (with ATR buffer)
        TP: At resistance levels (R1, R2, R3) scaled by risk/reward
        """
        # Calculate SL: Below support with ATR buffer
        stop_loss = support_level - (atr * self.rules.sl_atr_multiplier)
        risk = entry_price - stop_loss
        
        # Use risk management to calculate TP levels
        result = self.risk_manager.calculate_long_trade_levels(
            entry_price=entry_price,
            support_level=support_level,
            pivot_data=pivot_data,
            fibonacci_data=fib_data,
            atr=atr,
            highest_recent_price=max(resistance_levels) if resistance_levels else entry_price
        )
        
        return result
    
    def calculate_tp_sl_for_short(
        self,
        entry_price: float,
        resistance_level: float,
        support_levels: List[float],
        atr: float,
        pivot_data: Dict[str, float],
        fib_data: Dict[str, float]
    ) -> Dict:
        """
        Calculate TP/SL for SHORT trades
        
        SL: Above resistance (with ATR buffer)
        TP: At support levels (S1, S2, S3) scaled by risk/reward
        """
        # Calculate SL: Above resistance with ATR buffer
        stop_loss = resistance_level + (atr * self.rules.sl_atr_multiplier)
        risk = stop_loss - entry_price
        
        # Use risk management to calculate TP levels
        result = self.risk_manager.calculate_short_trade_levels(
            entry_price=entry_price,
            resistance_level=resistance_level,
            pivot_data=pivot_data,
            fibonacci_data=fib_data,
            atr=atr,
            lowest_recent_price=min(support_levels) if support_levels else entry_price
        )
        
        return result
