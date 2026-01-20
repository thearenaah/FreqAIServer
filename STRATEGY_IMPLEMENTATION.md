# Professional Trading Strategy Implementation

## Overview

This implementation uses an institutional-grade trading strategy that combines:
1. **EMA Support/Resistance Zones** (50 & 200-period)
2. **Pivot Points** (Baby Pips Floor method)
3. **Candle Pattern Recognition** (confirmation signals)
4. **RSI Filters** (overbought/oversold conditions)
5. **Price Action Analysis** (bounce/rejection from levels)

## Strategy Architecture

### Layer 1: Technical Indicators
- **EMA 50**: Fast trend confirmation (break above 200 for uptrend)
- **EMA 200**: Slow trend filter (break below 50 for downtrend)
- **RSI 14**: Momentum filter (>70 overbought, <30 oversold)

### Layer 2: Support/Resistance Levels
- **Floor Pivot Points**: (H + L + C) / 3
  - Resistance: R1, R2, R3
  - Support: S1, S2, S3
- **Tolerance-based Detection**: ±0.3% proximity to pivot level

### Layer 3: Entry Confirmation
- **Candle Patterns** validated at key levels:
  - Pin Bar (Hammer, Shooting Star) - reversal signals
  - Engulfing Pattern - trend confirmation
  - Outside Bar - breakout detection
  - Doji - indecision at levels
- **Pattern Strength** scoring (0.0-1.0 confidence)

### Layer 4: Rules Engine
- Combines all layers with specific entry/exit rules
- Generates confidence scores (0.0-1.0)
- Tracks reasoning for each signal decision

### Layer 5: Model Training
- **Labels**: Profitable trades (strategy said BUY and price went up)
- **Features**: All technical indicators + support/resistance proximity
- **ML Models**: RandomForest & GradientBoosting for pattern recognition
- **Confidence**: Combined from strategy + ML probabilities

---

## Entry Rules

### LONG Signal Requirements
1. **Price Action at Support**:
   - Price near support level (EMA 50, S1-S3, or recent low)
   - EMA 50 > EMA 200 (uptrend context)

2. **Candle Pattern Confirmation**:
   - Hammer at support (long lower wick)
   - OR Bullish engulfing (previous candle inside)
   - Minimum 0.5 strength confidence

3. **RSI Filter**:
   - RSI not extremely overbought (RSI < 85)
   - Bounce from oversold (RSI > 30) can confirm

4. **Price Action Bounce**:
   - Price bounces from support level
   - Close above high of confirmation candle

**Confidence Calculation**:
```
LONG_Confidence = 
  (0.3 * support_strength) +
  (0.3 * pattern_strength) +
  (0.2 * rsi_filter_score) +
  (0.2 * bounce_confirmation)
```

### SHORT Signal Requirements
1. **Price Action at Resistance**:
   - Price near resistance level (EMA 200, R1-R3, or recent high)
   - EMA 50 < EMA 200 (downtrend context)

2. **Candle Pattern Confirmation**:
   - Shooting Star at resistance (long upper wick)
   - OR Bearish engulfing (previous candle inside)
   - Minimum 0.5 strength confidence

3. **RSI Filter**:
   - RSI not extremely oversold (RSI > 15)
   - Rejection from overbought (RSI < 70) can confirm

4. **Price Action Rejection**:
   - Price rejects from resistance level
   - Close below low of confirmation candle

**Confidence Calculation**:
```
SHORT_Confidence = 
  (0.3 * resistance_strength) +
  (0.3 * pattern_strength) +
  (0.2 * rsi_filter_score) +
  (0.2 * rejection_confirmation)
```

---

## Exit Rules

### LONG Exit Strategies
1. **Profit Taking**:
   - R1, R2, or R3 (depending on risk/reward ratio)
   - Typical: R1 for 1:1, R2 for 1:2, R3 for 1:3

2. **Stop Loss**:
   - Below S1 (if entering at support)
   - Below EMA 50 (if EMA context broken)
   - Max 2% of entry price

3. **Early Exit Signals**:
   - Bearish engulfing above EMA 50
   - RSI > 85 (extreme overbought)
   - Close below 20-period SMA

### SHORT Exit Strategies
1. **Profit Taking**:
   - S1, S2, or S3 (depending on risk/reward ratio)
   - Typical: S1 for 1:1, S2 for 1:2, S3 for 1:3

2. **Stop Loss**:
   - Above R1 (if entering at resistance)
   - Above EMA 50 (if EMA context broken)
   - Max 2% of entry price

3. **Early Exit Signals**:
   - Bullish engulfing below EMA 50
   - RSI < 15 (extreme oversold)
   - Close above 20-period SMA

---

## Configuration Parameters

See `strategy_rules.py` for adjustable parameters:

```python
@dataclass
class StrategyRules:
    # EMA Periods
    ema_fast: int = 50
    ema_slow: int = 200
    
    # RSI Settings
    rsi_period: int = 14
    rsi_overbought: float = 70
    rsi_oversold: float = 30
    
    # Pivot Points
    use_camarilla: bool = False  # False = Floor, True = Camarilla
    pivot_tolerance: float = 0.003  # 0.3% proximity
    
    # Pattern Requirements
    require_pattern_confirmation: bool = True
    min_pattern_strength: float = 0.5
    
    # Confidence Thresholds
    min_signal_confidence: float = 0.5
    strong_signal_threshold: float = 0.7
```

---

## Module References

### `pivot_points.py`
Calculates support/resistance levels using pivot point methodology.

**Methods**:
- `calculate_floor_pivot(high, low, close)` → Dict with R1-R3, S1-S3
- `calculate_camarilla_pivot(high, low, close)` → Dict with R1-R4, S1-S4
- `calculate_woodie_pivot(high, low, close)` → Dict with R1-R2, S1-S2
- `find_nearest_pivot_level(price, pivot_data)` → (level_name, level_price, distance)

**Output Example**:
```python
{
    'R3': 1050.25,
    'R2': 1040.15,
    'R1': 1035.80,
    'Pivot': 1020.45,
    'S1': 1015.10,
    'S2': 1005.00,
    'S3': 994.90
}
```

### `candle_patterns.py`
Recognizes candle formations for entry confirmation.

**Methods**:
- `pin_bar(body, lower_wick, upper_wick, wick_threshold=0.7)` → (pattern, strength)
- `engulfing(current_body, prev_body, current_close, prev_open, current_open, prev_close)` → (pattern, strength)
- `outside_bar(current_high, current_low, prev_high, prev_low)` → bool
- `doji(body_ratio=0.05, wick_ratio=0.5)` → (pattern, strength)
- `detect_patterns(open, high, low, close, prev_open, prev_high, prev_low, prev_close)` → Dict

**Output Example**:
```python
{
    'pattern': 'hammer',
    'strength': 0.85,
    'upper_wick_ratio': 0.15,
    'lower_wick_ratio': 0.65,
    'body_ratio': 0.20,
    'type': 'bullish'
}
```

### `strategy_rules.py`
Defines exact entry/exit logic and evaluates confidence.

**Main Classes**:
- `Signal` - Enum: LONG, SHORT, HOLD
- `StrategyRules` - Configuration dataclass
- `StrategyEngine` - Evaluates rules and generates signals

**Key Methods**:
- `check_long_signal(price, ema_50, ema_200, rsi, pivot_data, candle_patterns, ...)` 
  → (Signal.LONG/HOLD, confidence: float, reasons: list)

- `check_short_signal(price, ema_50, ema_200, rsi, pivot_data, candle_patterns, ...)`
  → (Signal.SHORT/HOLD, confidence: float, reasons: list)

**Output Example**:
```python
signal = Signal.LONG
confidence = 0.72
reasons = [
    "Price at support S1 (0.15% away)",
    "Hammer pattern detected (strength 0.85)",
    "EMA 50 > EMA 200 (uptrend)",
    "RSI 45 (neutral, good entry zone)",
    "Candle closed above previous high (bounce confirmed)"
]
```

### `features.py`
Feature engineering with professional strategy integration.

**Methods**:
- `calculate_price_features(df)` → Dict with standard technical indicators
- `calculate_professional_features(df, include_patterns)` → Dict with:
  - `ema_50`, `ema_200`, `ema_trend`
  - `rsi`
  - `pivot_points` (full pivot data)
  - `candle_patterns` (pattern detection results)
  - `recent_price_action` (current market structure)
  - `signal_analysis` (strategy engine output)

---

## Training Data Labels

Labels are generated using the strategy engine:

**Label = 1** (Profitable Trade):
- Strategy generated LONG signal AND price went up next candle
- OR Strategy generated SHORT signal AND price went down next candle

**Label = 0** (Unprofitable/No Signal):
- Strategy said HOLD (below confidence threshold)
- OR Strategy signal was opposite to actual price direction
- OR No clear signal

This means the ML model learns to:
1. Recognize patterns that the strategy identifies
2. Filter false signals
3. Improve confidence scoring
4. Suggest risk management based on actual outcomes

---

## Prediction & Signal Generation

The prediction pipeline:

```
Historical Data
    ↓
Feature Calculation (EMA, RSI, Pivots, Patterns)
    ↓
Strategy Engine (Exact Rules)
    ├─→ LONG Signal (confidence 0.72)
    ├─→ SHORT Signal (confidence 0.45)
    └─→ Final Decision: LONG (use higher confidence)
    ↓
ML Model Prediction (For confidence refinement)
    ├─→ Probability LONG: 0.68
    ├─→ Probability SHORT: 0.32
    └─→ Agrees with strategy: Yes ✓
    ↓
Final Signal: LONG
Final Confidence: 0.72 (from strategy)
Reasoning: Comprehensive list of factors
```

### Response Fields

```json
{
  "signal": "LONG",
  "confidence": 0.72,
  "ml_probability": 0.68,
  "ml_signal": "LONG",
  "strategy_signal": "LONG",
  "strategy_confidence": 0.72,
  "reasons": [
    "Price at support S1 (0.15% away)",
    "Hammer pattern detected (strength 0.85)",
    "EMA 50 > EMA 200 (uptrend)",
    "RSI 45 (neutral, good entry zone)",
    "ML model confidence: 0.68 (LONG)"
  ],
  "pivot_points": {
    "R1": 1050.25,
    "S1": 1015.10,
    ...
  },
  "candle_patterns": {
    "pattern": "hammer",
    "strength": 0.85,
    ...
  }
}
```

---

## Professional Standards

### Risk Management
- **Position Sizing**: 2% risk per trade (configurable)
- **Risk/Reward**: Minimum 1:2 (stop loss half the target distance)
- **Max Drawdown**: 20% of account (circuit breaker)

### Backtesting
Before deploying:
1. Test on 2+ years of historical data
2. Verify win rate ≥ 50% (with proper risk/reward)
3. Check max drawdown tolerance
4. Verify pattern detection accuracy

### Live Validation
After deployment:
1. Paper trading for 1 month minimum
2. Monitor signal accuracy
3. Track confidence vs actual outcomes
4. Adjust parameters based on live results

---

## Example Usage

### Generating a Signal

```python
from strategy_rules import StrategyEngine, StrategyRules
from pivot_points import PivotPoints
from candle_patterns import CandlePatterns
import pandas as pd

# Setup
rules = StrategyRules()
engine = StrategyEngine(rules)
df = pd.read_csv('BTCUSD_1h.csv')

# Calculate indicators
ema_50 = df['close'].ewm(span=50).mean().iloc[-1]
ema_200 = df['close'].ewm(span=200).mean().iloc[-1]
rsi = calculate_rsi(df['close'].values)[-1]

# Get pivots
pivots = PivotPoints.calculate_floor_pivot(
    df['high'].iloc[-2],
    df['low'].iloc[-2],
    df['close'].iloc[-2]
)

# Get patterns
patterns = CandlePatterns.detect_patterns(
    df['open'].iloc[-1], df['high'].iloc[-1],
    df['low'].iloc[-1], df['close'].iloc[-1],
    df['open'].iloc[-2], df['high'].iloc[-2],
    df['low'].iloc[-2], df['close'].iloc[-2]
)

# Get signal
signal, confidence, reasons = engine.check_long_signal(
    price=df['close'].iloc[-1],
    ema_50=ema_50,
    ema_200=ema_200,
    rsi=rsi,
    pivot_data=pivots,
    candle_patterns=patterns,
    recent_price_action={
        'current_price': df['close'].iloc[-1],
        'highest_price': df['high'].iloc[-5:].max(),
        'lowest_price': df['low'].iloc[-5:].min(),
    }
)

print(f"Signal: {signal.value}")
print(f"Confidence: {confidence:.2%}")
for reason in reasons:
    print(f"  - {reason}")
```

### Integration with Django

See `DJANGO_INTEGRATION.md` for:
- Celery task setup for async predictions
- API endpoint configuration
- Database synchronization
- Real-time signal delivery to users

---

## Troubleshooting

### Low Signal Confidence
- Check if price is at key levels (EMAs, pivots)
- Verify pattern detection (ensure clear formations)
- Review RSI conditions (not in extreme zones)

### False Signals
- Increase `min_pattern_strength` threshold
- Reduce `pivot_tolerance` (tighter level detection)
- Require stronger EMA confirmation (>200 points between 50/200)

### Missed Opportunities
- Decrease `min_pattern_strength` threshold
- Increase `pivot_tolerance` (wider level detection)
- Consider weaker EMA trend filter

---

## References

### Baby Pips Pivot Points
https://www.babypips.com/forexpedia/floor-pivot-points

### Candle Pattern Recognition
https://www.investopedia.com/terms/c/candlestick.asp

### RSI Indicator
https://www.investopedia.com/terms/r/rsi.asp

### EMA Moving Averages
https://www.investopedia.com/terms/e/ema.asp
