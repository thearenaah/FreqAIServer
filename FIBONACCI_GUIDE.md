# Fibonacci Levels in Trading Strategy

## 📊 What Are Fibonacci Levels?

Fibonacci numbers are a mathematical sequence where each number is the sum of the two preceding numbers:
```
1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610...
```

In trading, Fibonacci levels derived from these numbers are used to identify potential support and resistance levels.

---

## 🔢 Key Fibonacci Ratios

### Retracement Levels (Pullbacks)
Used to find support during downtrends or resistance during uptrends:

| Ratio | Percentage | Strength | Use Case |
|-------|-----------|----------|----------|
| 0.236 | **23.6%** | ⭐ Weak | Early retracement, breakout |
| 0.382 | **38.2%** | ⭐⭐⭐ Strong | Common entry level |
| 0.500 | **50.0%** | ⭐⭐⭐ Strong | Psychological level |
| 0.618 | **61.8%** | ⭐⭐⭐⭐ Very Strong | Golden Ratio - Strongest |
| 0.786 | **78.6%** | ⭐⭐ Moderate | Deep retracement |

### Extension Levels (Targets)
Used to find profit targets when price breaks to new highs:

| Ratio | Percentage | Use Case |
|-------|-----------|----------|
| 1.618 | **161.8%** | First extension target |
| 2.618 | **261.8%** | Second extension target |
| 4.236 | **423.6%** | Third extension target |

---

## 📐 How to Calculate Fibonacci Levels

### Formula for Retracements
```
Move = High - Low
Retracement Level = High - (Move × Fibonacci Ratio)

Example:
High = 100
Low = 80
Move = 100 - 80 = 20

38.2% Retracement = 100 - (20 × 0.382) = 100 - 7.64 = 92.36
61.8% Retracement = 100 - (20 × 0.618) = 100 - 12.36 = 87.64
```

### Formula for Extensions
```
Extension Level = High + (Move × (Ratio - 1.0))

Example:
100 + (20 × (1.618 - 1.0)) = 100 + 12.36 = 112.36  (161.8%)
100 + (20 × (2.618 - 1.0)) = 100 + 32.36 = 132.36  (261.8%)
```

---

## 🎯 Using Fibonacci in Trading

### Entry Signals

#### LONG Entries
1. **Price bounces from 38.2% or 61.8% retracement**
   - Most reliable Fibonacci levels
   - Combined with EMA confirmation
   - Pattern confirmation increases confidence

2. **Price bounces from 50% retracement**
   - Psychological level (halfway point)
   - Often acts as support in strong uptrends
   - Good entry with candle pattern

#### SHORT Entries
1. **Price rejects from 38.2% or 61.8% retracement**
   - From downtrend perspective
   - Resistance in downtrending markets
   - Combined with bearish patterns

---

### Exit Signals (Profit Targets)

#### LONG Trade Targets
```
Entry at 61.8% retracement → Target 1: 161.8% extension
                           → Target 2: 261.8% extension
                           → Target 3: 423.6% extension
```

#### SHORT Trade Targets
```
Entry at 38.2% retracement → Target 1: 161.8% extension (downward)
                            → Target 2: 261.8% extension (downward)
                            → Target 3: 423.6% extension (downward)
```

---

## 🔍 Fibonacci Confluence

**Confluence** = Multiple levels aligning at same price zone

### Strongest Signals Occur When:
1. ✅ Price at Fibonacci level (38.2%, 50%, 61.8%)
2. ✅ AND at Pivot Point level (Floor/Camarilla)
3. ✅ AND at EMA level (50 or 200)
4. ✅ AND strong candle pattern
5. ✅ AND RSI in good zone

**Confluence Score**: 3+ levels = Strong signal (0.7-1.0 confidence)

### Example
```
Price = 62,450

Fibonacci 61.8% = 62,456 ✓ (Close match!)
Pivot S1 = 62,420 ✓ (Within tolerance)
EMA 50 = 62,400 ✓ (Nearby)

→ Strong confluence zone
→ High probability bounce zone
→ Good entry signal
```

---

## 📊 Fibonacci Implementation

### Module: `fibonacci_levels.py`

#### Main Functions

**`calculate_retracements(swing_high, swing_low, include_extensions=False)`**
```python
# Returns dictionary of all retracement levels
from fibonacci_levels import FibonacciLevels

levels = FibonacciLevels.calculate_retracements(
    swing_high=100,
    swing_low=80,
    include_extensions=True
)

# Output:
# {
#     '23.6%': {'level': 95.28, 'type': 'retracement', ...},
#     '38.2%': {'level': 92.36, 'type': 'retracement', ...},
#     '50.0%': {'level': 90.00, 'type': 'retracement', ...},
#     '61.8%': {'level': 87.64, 'type': 'retracement', ...},
#     '161.8%': {'level': 112.36, 'type': 'extension', ...},
#     ...
# }
```

**`find_nearest_fibonacci_level(price, levels_dict, tolerance=0.003)`**
```python
# Find the closest Fibonacci level to current price
nearest_name, nearest_level, distance = FibonacciLevels.find_nearest_fibonacci_level(
    price=92.00,
    levels_dict=levels,
    tolerance=0.003  # 0.3% tolerance
)

# Output: ('38.2%', level_data, 0.0039)  # 0.39% away
```

**`analyze_price_action_at_fibonacci(price, levels_dict, tolerance=0.003)`**
```python
# Detailed analysis if price is at Fibonacci level
analysis = FibonacciLevels.analyze_price_action_at_fibonacci(
    price=92.40,
    levels_dict=levels,
    tolerance=0.003
)

# Output:
# {
#     'at_level': True,
#     'nearest_level': '38.2%',
#     'distance': 0.0004,
#     'confidence': 0.87,
#     'level_type': 'retracement',
#     'description': 'Fibonacci 38.2% Retracement'
# }
```

**`identify_fibonacci_bounce(price, previous_close, swing_high, swing_low, tolerance=0.003)`**
```python
# Detect if price is bouncing from Fibonacci support
bounce = FibonacciLevels.identify_fibonacci_bounce(
    price=92.40,
    previous_close=91.80,
    swing_high=100,
    swing_low=80
)

# Output:
# {
#     'bouncing': True,
#     'nearest_level': '38.2%',
#     'bounce_strength': 0.72,
#     'direction': 'up',
#     'description': 'Bouncing UP from 38.2% Fibonacci level'
# }
```

---

## 🤖 Integration with Strategy Rules

### In `strategy_rules.py`

The `StrategyEngine` now includes:

**`evaluate_fibonacci_support(price, fibonacci_data)`**
- Evaluates how strong a Fibonacci support level is
- Considers distance to level and which level it is
- Golden Ratio (61.8%) weighted higher
- Returns 0-1 confidence

**`evaluate_fibonacci_resistance(price, fibonacci_data)`**
- Same as support but for resistance (bearish)
- Used in SHORT signal evaluation

**`evaluate_fibonacci_confluence(price, fibonacci_data, pivot_data, ema_50, ema_200)`**
- Calculates how many key levels are near current price
- Combines: Fibonacci + Pivots + EMAs
- Returns confluence score and reason
- Multiple confluence = stronger signal

### Configuration in `StrategyRules`

```python
@dataclass
class StrategyRules:
    # Fibonacci Settings
    use_fibonacci: bool = True                    # Enable Fibonacci analysis
    fibonacci_tolerance: float = 0.003            # 0.3% proximity tolerance
    fibonacci_min_strength: float = 0.4           # Minimum confidence for signal
```

---

## 📈 Practical Example

### Scenario: BTCUSD 1-Hour Chart

```
Swing High: 65,000
Swing Low: 60,000
Move: 5,000

Fibonacci Levels:
  61.8% Retracement: 61,810
  50.0% Retracement: 62,500
  38.2% Retracement: 63,090

Current Price: 61,850
  → Price at 61.8% retracement (bounce zone)
  → Expected bouncy behavior

Pivot Points:
  S1: 61,900
  Pivot: 62,250
  R1: 62,600

Confluence:
  ✓ Fibonacci 61.8% = 61,810
  ✓ Pivot S1 = 61,900
  ✓ EMA 50 = 61,920
  
  → 3-level confluence
  → Strong support zone
  → High probability bounce
  → Good LONG entry

Candle Pattern:
  Hammer detected (strength 0.85)
  
SIGNAL: LONG
Confidence: 0.75 (high)
Reasons:
  - Price at Fibonacci 61.8% (0.05% away)
  - Strong confluence with Pivot S1
  - Hammer pattern confirmed
  - EMA 50 nearby
  - RSI 42 (good zone)
```

---

## 🎓 Key Takeaways

### Why Fibonacci Works
1. **Mathematical**: Based on natural sequence found in nature
2. **Psychological**: Traders worldwide use same levels
3. **Confluence**: Multiple methods identify same zones
4. **Flexible**: Works across all timeframes and assets

### Best Practices
1. ✅ Use with other indicators (not alone)
2. ✅ Combine with EMA for trend confirmation
3. ✅ Wait for candle pattern at Fibonacci level
4. ✅ Use confluence zones (2+ indicators)
5. ✅ Backtest on your trading assets
6. ✅ Adjust tolerance based on volatility

### Common Mistakes
1. ❌ Trading Fibonacci levels without confluence
2. ❌ Using 23.6% as strong level (it's weak)
3. ❌ Ignoring EMA trend when trading Fibonacci
4. ❌ No pattern confirmation at Fibonacci level
5. ❌ Fixed tolerance (should vary by volatility)

---

## 📊 Fibonacci Configuration Tips

### For Fast Markets (High Volatility)
```python
fibonacci_tolerance: 0.005        # 0.5% wider tolerance
fibonacci_min_strength: 0.3       # Lower threshold
use_camarilla: True               # More sensitive pivots
```

### For Slow Markets (Low Volatility)
```python
fibonacci_tolerance: 0.002        # 0.2% tighter tolerance
fibonacci_min_strength: 0.5       # Higher threshold
use_camarilla: False              # Floor pivots
```

### For Strong Trends
```python
fibonacci_min_strength: 0.6       # Only strong levels
require_ema_alignment: True       # Must align with EMA trend
```

---

## 🔗 Resources

- **Baby Pips Fibonacci**: https://www.babypips.com/forexpedia/fibonacci-retracements
- **Wikipedia Fibonacci**: https://en.wikipedia.org/wiki/Fibonacci_number
- **Trading Strategy**: See `STRATEGY_IMPLEMENTATION.md` and `QUICK_REFERENCE.md`

---

## 📁 Files Updated

1. **fibonacci_levels.py** (NEW)
   - Complete Fibonacci implementation
   - Retracements, extensions, bounce detection
   - Confluence analysis

2. **strategy_rules.py** (UPDATED)
   - Added Fibonacci configuration to StrategyRules
   - Added Fibonacci evaluation methods
   - Added confluence detection method

3. **features.py** (UPDATED)
   - Fibonacci calculation in professional features
   - Fibonacci bounce detection
   - Confluence scoring in signal analysis

---

## ✅ Integration Status

- ✅ Fibonacci levels calculation (all 3 methods)
- ✅ Retracement and extension levels
- ✅ Bounce and breakout detection
- ✅ Confluence detection (Fib + Pivot + EMA)
- ✅ Strategy engine integration
- ✅ Feature engineering integration
- ✅ Confidence scoring with Fibonacci
- ✅ Complete documentation

**Status**: PRODUCTION READY 🚀

---

*Last Updated*: 2024  
*Module*: fibonacci_levels.py  
*Integration*: Complete with Strategy Rules and Features
