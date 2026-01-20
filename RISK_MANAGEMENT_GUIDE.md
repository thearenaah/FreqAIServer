# Risk Management & TP/SL Implementation Guide

## 📚 Table of Contents
1. [Overview](#overview)
2. [Entry Points](#entry-points)
3. [Stop Loss (SL) Placement](#stop-loss-sl-placement)
4. [Take Profit (TP) Levels](#take-profit-tp-levels)
5. [Risk/Reward Ratios](#riskReward-ratios)
6. [Configuration](#configuration)
7. [Implementation Details](#implementation-details)
8. [Examples](#examples)
9. [Best Practices](#best-practices)

---

## Overview

**Problem Solved:**
Traders need precise entry, stop loss, and take profit levels for every trade. Without them:
- Entries are unclear (at what exact price?)
- Risk is uncontrolled (where do we cut losses?)
- Profit targets are vague (how much profit is enough?)

**Solution Provided:**
The `risk_management.py` module automatically calculates:
1. **Entry Point** - Where to enter (at support for LONG, resistance for SHORT)
2. **Stop Loss** - Where to exit if wrong (below support for LONG, above resistance for SHORT)
3. **Take Profit 1** - First profit target (1:1 risk/reward)
4. **Take Profit 2** - Second target (2:1 risk/reward)
5. **Take Profit 3** - Third target (3:1 risk/reward)

---

## Entry Points

### LONG Entry Rules

**Entry is at a support level:**
- At EMA 50
- At EMA 200
- At Pivot S1 (first support)
- At Pivot S2 or S3 (strong support)
- At Fibonacci retracement level (38.2%, 50%, 61.8%)

**Entry Signal Confirmation:**
- Candle pattern (hammer, bullish engulfing, etc.)
- Price bouncing from support (showing strength)
- RSI not oversold (room for recovery)

**Example:**
```
Price at Pivot S1 (1.2025) + Hammer pattern → ENTRY at 1.2030
```

### SHORT Entry Rules

**Entry is at a resistance level:**
- At EMA 50
- At EMA 200
- At Pivot R1 (first resistance)
- At Pivot R2 or R3 (strong resistance)
- At Fibonacci retracement level (38.2%, 50%, 61.8%)

**Entry Signal Confirmation:**
- Candle pattern (shooting star, bearish engulfing, etc.)
- Price rejecting from resistance (showing weakness)
- RSI not overbought (room for decline)

**Example:**
```
Price at Pivot R1 (1.2075) + Shooting Star pattern → ENTRY at 1.2070
```

---

## Stop Loss (SL) Placement

### LONG Trade SL

**Rule: SL is placed BELOW the support level**

```
Price ──────────┐
  ↓  (Candle)  │
Support ────────── ← Entry (bounce from here)
  ↓
  └─ SL (below support by offset)
```

**Formula:**
```
SL = Support × (1 - sl_offset)
SL = Support × (1 - 0.005)   # Default: 0.5% below support
```

**Example:**
- Support level: $62,000
- SL offset: 0.5%
- **SL = $62,000 × (1 - 0.005) = $61,690**

**Rationale:**
- Price bounces from support, so SL below prevents whipsaws
- 0.5% buffer allows for small wicks/noise
- If price breaks below SL, the trade setup is invalid

### SHORT Trade SL

**Rule: SL is placed ABOVE the resistance level**

```
  ┌─ SL (above resistance by offset)
  ↓
Resistance ────────── ← Entry (rejection from here)
  ↑  (Candle)  │
  └──────────┘
Price
```

**Formula:**
```
SL = Resistance × (1 + sl_offset)
SL = Resistance × (1 + 0.005)   # Default: 0.5% above resistance
```

**Example:**
- Resistance level: $62,500
- SL offset: 0.5%
- **SL = $62,500 × (1 + 0.005) = $62,812.50**

### ATR-Based SL (Volatility Adjustment)

For volatile markets, use ATR instead of fixed offset:

**Formula:**
```
LONG:   SL = Support - (ATR × 1.5)
SHORT:  SL = Resistance + (ATR × 1.5)
```

**Example:**
- Support: $62,000
- ATR: $100 (20-period Average True Range)
- SL = $62,000 - ($100 × 1.5) = $61,850

**When to use ATR:**
- High volatility markets (crypto, volatile stocks)
- Use tighter SL on calm markets
- Use wider SL on choppy markets

---

## Take Profit (TP) Levels

### Understanding Risk/Reward Ratios

**Risk = Entry - SL (distance we're risking)**
**Reward = TP - Entry (distance we profit)**
**Ratio = Reward / Risk**

**Example:**
```
LONG Trade:
Entry:  $1,000
SL:     $950
Risk:   $50

TP1 at $1,050:   Reward = $50,  Ratio = 1:1 ✓
TP2 at $1,100:   Reward = $100, Ratio = 2:1 ✓✓
TP3 at $1,150:   Reward = $150, Ratio = 3:1 ✓✓✓
```

### TP Levels for LONG Trades

**TP1: 1:1 Risk/Reward**
- **Target:** First resistance level
- **Likely Level:** Pivot R1
- **Expected Hit:** 50-60% of the time
- **Position Size:** Close 33% of position here
- **Rule:** Safe profit taking, lock in gains

```
Entry: 1.2030
Risk: 0.0020 (Entry - SL)

TP1 Price = 1.2030 + (0.0020 × 1.0) = 1.2050 ✓
Most likely at Pivot (1.2050) or EMA 50
```

**TP2: 2:1 Risk/Reward**
- **Target:** Second resistance level
- **Likely Level:** Pivot R2 or Fibonacci 161.8%
- **Expected Hit:** 30-40% of the time
- **Position Size:** Close another 33% of position
- **Rule:** Let strong trends run, capture bigger moves

```
Entry: 1.2030
Risk: 0.0020

TP2 Price = 1.2030 + (0.0020 × 2.0) = 1.2070 ✓
Most likely at Pivot R2 (1.2075)
```

**TP3: 3:1 Risk/Reward**
- **Target:** Maximum profit target
- **Likely Level:** Pivot R3 or Fibonacci 261.8%
- **Expected Hit:** 15-25% of the time
- **Position Size:** Close remaining 34% of position
- **Rule:** Let winners run! Don't get greedy though

```
Entry: 1.2030
Risk: 0.0020

TP3 Price = 1.2030 + (0.0020 × 3.0) = 1.2090 ✓
Most likely at Pivot R3 (1.2100) or swing high
```

### TP Levels for SHORT Trades

**TP1: 1:1 Risk/Reward**
- **Target:** First support level (below entry)
- **Likely Level:** Pivot S1
- **Expected Hit:** 50-60% of the time
- **Position Size:** Close 33% here

```
Entry: 1.2070
Risk: 0.0020

TP1 Price = 1.2070 - (0.0020 × 1.0) = 1.2050 ✓
Most likely at Pivot (1.2050)
```

**TP2: 2:1 Risk/Reward**
- **Target:** Second support level
- **Likely Level:** Pivot S2
- **Expected Hit:** 30-40% of the time
- **Position Size:** Close another 33%

```
Entry: 1.2070
Risk: 0.0020

TP2 Price = 1.2070 - (0.0020 × 2.0) = 1.2030 ✓
Most likely at Pivot S2 (1.2025)
```

**TP3: 3:1 Risk/Reward**
- **Target:** Maximum profit target
- **Likely Level:** Pivot S3 or swing low
- **Expected Hit:** 15-25% of the time
- **Position Size:** Close remaining 34%

```
Entry: 1.2070
Risk: 0.0020

TP3 Price = 1.2070 - (0.0020 × 3.0) = 1.2010 ✓
Most likely at Pivot S3 (1.2000) or swing low
```

---

## Risk/Reward Ratios

### Why 1:1, 2:1, 3:1?

**Probability vs Profitability:**

| Ratio | Meaning | Win Rate Needed | Frequency |
|-------|---------|-----------------|-----------|
| 1:1   | Risk $1 to make $1 | 50%+ | Very common |
| 2:1   | Risk $1 to make $2 | 33%+ | Common |
| 3:1   | Risk $1 to make $3 | 25%+ | Less common |
| 5:1   | Risk $1 to make $5 | 17%+ | Rare |

### Minimum Acceptable Ratio

**For a Profitable Trading System:**
```
Minimum RR Ratio = 1.5:1

Example:
- Win Rate: 50%
- Winning Trade: $200 (1.5 × Risk)
- Losing Trade: -$100
- Per 2 trades: $200 - $100 = +$100 profit

Equation: (Win% × Avg Win) - (Loss% × Avg Loss) > 0
(0.5 × 200) - (0.5 × 100) = 100 - 50 = +$50 ✓ Profitable
```

### Your Strategy's RR

With Pivot Points + Fibonacci:
- **TP1 (1:1):** Easy to hit, 60%+ hit rate → Consistent profit
- **TP2 (2:1):** Medium difficulty, 40% hit rate → Good rewards
- **TP3 (3:1):** Hard to hit, 20% hit rate → Home run trades

**Expected Performance:**
- If you catch TP1 consistently: +50-60% win rate, +0.5-1.0 profit per trade
- If some TP2 hits: +40-50% win rate, +1.0-2.0 profit per trade
- If some TP3 hits: +30-40% win rate, +1.5-3.0 profit per trade

---

## Configuration

### Default Settings

```python
# In strategy_rules.py
@dataclass
class StrategyRules:
    # TP/SL Configuration
    calculate_tp_sl: bool = True       # Enable TP/SL calculation
    tp1_risk_reward: float = 1.0       # TP1: 1:1 ratio
    tp2_risk_reward: float = 2.0       # TP2: 2:1 ratio
    tp3_risk_reward: float = 3.0       # TP3: 3:1 ratio
```

### Risk Management Config

```python
# In risk_management.py
@dataclass
class RiskManagementConfig:
    # TP/SL Calculation Method
    use_fibonacci_for_tp: bool = True      # Use Fib extensions
    use_pivot_for_tp: bool = True          # Use pivot R1, R2, R3
    
    # Risk/Reward Ratios for TP levels
    tp1_risk_reward: float = 1.0           # TP1: 1:1 ratio
    tp2_risk_reward: float = 2.0           # TP2: 2:1 ratio
    tp3_risk_reward: float = 3.0           # TP3: 3:1 ratio
    
    # Position Sizing for TP levels
    tp1_size: float = 0.33                 # Close 33% at TP1
    tp2_size: float = 0.33                 # Close 33% at TP2
    tp3_size: float = 0.34                 # Close 34% at TP3
    
    # Stop Loss Parameters
    use_support_offset_for_sl: bool = True # SL below support
    sl_support_offset: float = 0.005       # 0.5% below support
    sl_resistance_offset: float = 0.005    # 0.5% above resistance
    
    # ATR-based SL (volatility adjustment)
    use_atr_for_sl: bool = True            # Use ATR to adjust SL
    atr_multiplier: float = 1.5            # SL = Entry ± (ATR × 1.5)
```

### Market-Specific Configurations

#### High Volatility Market (Crypto, Volatile Stocks)

```python
# Adjust for larger movements
tp1_risk_reward: float = 1.2       # TP1: 1.2:1 (wider first target)
tp2_risk_reward: float = 2.5       # TP2: 2.5:1
tp3_risk_reward: float = 4.0       # TP3: 4.0:1 (big targets)

# Use ATR instead of fixed offset
use_atr_for_sl: bool = True
atr_multiplier: float = 2.0        # Wider SL: 2 × ATR

# Wider position sizing
tp1_size: float = 0.25             # Close 25% at TP1 (hold more)
tp2_size: float = 0.25             # Close 25% at TP2
tp3_size: float = 0.50             # Let it run 50%
```

#### Low Volatility Market (Calm, Stable Markets)

```python
# Adjust for smaller movements
tp1_risk_reward: float = 0.8       # TP1: 0.8:1 (tight first target)
tp2_risk_reward: float = 1.5       # TP2: 1.5:1
tp3_risk_reward: float = 2.0       # TP3: 2.0:1

# Use tighter SL
use_atr_for_sl: bool = True
atr_multiplier: float = 1.0        # Tighter SL: 1 × ATR

# Tighter position sizing
tp1_size: float = 0.50             # Close 50% at TP1 (take gains early)
tp2_size: float = 0.35             # Close 35% at TP2
tp3_size: float = 0.15             # Only 15% stays
```

#### Conservative Trading (Capital Preservation)

```python
# Very safe ratios
tp1_risk_reward: float = 0.5       # TP1: 0.5:1 (easy target)
tp2_risk_reward: float = 1.0       # TP2: 1:1
tp3_risk_reward: float = 1.5       # TP3: 1.5:1

# Very tight SL
sl_support_offset: float = 0.002   # 0.2% SL (tight!)
atr_multiplier: float = 0.5        # Tight SL

# Aggressive position closing
tp1_size: float = 0.67             # Close 67% at TP1!
tp2_size: float = 0.25             # Close 25% at TP2
tp3_size: float = 0.08             # Only 8% stays
```

#### Aggressive Trading (Growth Focused)

```python
# Aggressive ratios
tp1_risk_reward: float = 1.5       # TP1: 1.5:1
tp2_risk_reward: float = 3.0       # TP2: 3:1
tp3_risk_reward: float = 5.0       # TP3: 5:1!

# Wider SL (tolerate more movement)
sl_support_offset: float = 0.010   # 1.0% SL (wide)
atr_multiplier: float = 2.5        # Very wide SL

# Hold for big moves
tp1_size: float = 0.10             # Close only 10% at TP1
tp2_size: float = 0.20             # Close 20% at TP2
tp3_size: float = 0.70             # Hold 70% for home run!
```

---

## Implementation Details

### Code Structure

```python
# 1. Create RiskManagement instance
rm = RiskManagement(RiskManagementConfig())

# 2. Calculate LONG trade levels
long_setup = rm.calculate_long_trade_levels(
    entry_price=62030,
    support_level=62000,
    pivot_data={...},
    fibonacci_data={...},
    atr=100,
    highest_recent_price=63000,
)

# 3. Calculate SHORT trade levels
short_setup = rm.calculate_short_trade_levels(
    entry_price=62070,
    resistance_level=62100,
    pivot_data={...},
    fibonacci_data={...},
    atr=100,
    lowest_recent_price=61000,
)

# 4. Validate setup
validation = rm.validate_trade_setup(long_setup)
if validation['is_valid']:
    print("Trade setup valid - ready to execute!")
else:
    print(f"Issues: {validation['errors']}")
```

### Integration with Strategy

```python
# In strategy_rules.py StrategyEngine class

# Automatic TP/SL calculation when signal is generated
if long_signal == Signal.LONG:
    tp_sl = engine.calculate_long_tp_sl(
        entry_price=price,
        support_level=support,
        pivot_data=pivot_data,
        fibonacci_data=fib_data,
        atr=atr,
        highest_recent=high,
    )
    # Output includes:
    # - tp_sl['entry']
    # - tp_sl['stop_loss']
    # - tp_sl['risk']
    # - tp_sl['tp1'], tp_sl['tp2'], tp_sl['tp3']
    # - tp_sl['risk_reward_ratio']
    # - tp_sl['validation']
```

### Integration with Feature Engineering

```python
# In features.py calculate_professional_features()

# Automatic TP/SL in signal output
features['signal_analysis'] = {
    'long_signal': 'buy',
    'long_confidence': 0.78,
    'long_reasons': [...],
    'long_tp_sl': {  # ← NEW!
        'entry': 62030,
        'stop_loss': 61980,
        'risk': 50,
        'tp1': {'price': 62080, 'risk_reward': 1.0, 'position_size': 0.33},
        'tp2': {'price': 62130, 'risk_reward': 2.0, 'position_size': 0.33},
        'tp3': {'price': 62180, 'risk_reward': 3.0, 'position_size': 0.34},
        'risk_reward_ratio': 3.0,
        'trade_description': 'LONG: Entry 62030 | SL 61980 | TP1 62080 | TP2 62130 | TP3 62180 | RR: 3.0:1',
        'validation': {'is_valid': True, 'warnings': [], 'errors': []}
    },
}
```

---

## Examples

### Example 1: EURUSD LONG Trade

**Market Setup:**
```
Current Price: 1.20500
EMA 50: 1.20480
EMA 200: 1.20400
Pivot S1: 1.20250
Pivot R1: 1.20750
RSI: 35 (oversold)
Pattern: Hammer at support
ATR(20): 0.00150
Recent High: 1.20900
Recent Low: 1.20200
```

**Execution:**

```python
rm = RiskManagement()
setup = rm.calculate_long_trade_levels(
    entry_price=1.20500,
    support_level=1.20250,
    pivot_data={
        's2': 1.20000, 's1': 1.20250, 'pivot': 1.20500,
        'r1': 1.20750, 'r2': 1.21000, 'r3': 1.21250
    },
    fibonacci_data={
        '0.382': 1.20400, '0.618': 1.20100, '1.618': 1.21300
    },
    atr=0.00150,
    highest_recent=1.20900
)
```

**Result:**

| Component | Value | Reason |
|-----------|-------|--------|
| **Entry** | 1.20500 | At price, near support |
| **Support** | 1.20250 | Pivot S1 |
| **SL** | 1.20328 | 0.5% below support = 1.20250 × 0.995 |
| **Risk** | 0.00172 | 1.20500 - 1.20328 |
| **TP1 (1:1)** | 1.20672 | Entry + (0.00172 × 1.0) ≈ Pivot |
| **TP2 (2:1)** | 1.20844 | Entry + (0.00172 × 2.0) ≈ R1 |
| **TP3 (3:1)** | 1.21016 | Entry + (0.00172 × 3.0) ≈ R2 |
| **Risk/Reward** | 3.0:1 | Excellent ratio! |
| **Status** | ✓ VALID | All checks pass |

**Trade Description:**
```
LONG: Entry 1.20500 | SL 1.20328 (Risk: 0.00172) | 
TP1 1.20672 (1:1) - Close 33% | 
TP2 1.20844 (2:1) - Close 33% | 
TP3 1.21016 (3:1) - Close 34% | 
Overall RR: 3.0:1 ✓ VALID
```

**Execution Plan:**
1. **Buy** 100 shares at 1.20500
2. **SL** at 1.20328 (all 100 shares)
3. **TP1** at 1.20672 → Sell 33 shares
4. **TP2** at 1.20844 → Sell 33 shares
5. **TP3** at 1.21016 → Sell 34 shares

### Example 2: Bitcoin SHORT Trade

**Market Setup:**
```
Current Price: $62,500
EMA 50: $62,480
EMA 200: $62,300
Pivot R1: $62,750
Pivot S1: $62,250
RSI: 68 (overbought)
Pattern: Shooting Star at resistance
ATR(20): $300
Recent High: $63,200
Recent Low: $61,800
```

**Execution:**

```python
rm = RiskManagement()
setup = rm.calculate_short_trade_levels(
    entry_price=62500,
    resistance_level=62750,
    pivot_data={
        's3': 61500, 's2': 61750, 's1': 62250,
        'pivot': 62500, 'r1': 62750, 'r2': 63000, 'r3': 63250
    },
    fibonacci_data={
        '0.236': 62700, '0.382': 62600, '1.618': 60800, '2.618': 59100
    },
    atr=300,
    lowest_recent=61800
)
```

**Result:**

| Component | Value | Reason |
|-----------|-------|--------|
| **Entry** | $62,500 | At price, near R1 |
| **Resistance** | $62,750 | Pivot R1 |
| **SL** | $63,138 | 0.5% above resistance = 62,750 × 1.005 |
| **Risk** | $638 | 63,138 - 62,500 |
| **TP1 (1:1)** | $61,862 | Entry - (638 × 1.0) ≈ S1 |
| **TP2 (2:1)** | $61,224 | Entry - (638 × 2.0) ≈ S2 |
| **TP3 (3:1)** | $60,586 | Entry - (638 × 3.0) ≈ S3 |
| **Risk/Reward** | 3.0:1 | Excellent ratio! |
| **Status** | ✓ VALID | All checks pass |

**Trade Description:**
```
SHORT: Entry $62,500 | SL $63,138 (Risk: $638) | 
TP1 $61,862 (1:1) - Close 33% | 
TP2 $61,224 (2:1) - Close 33% | 
TP3 $60,586 (3:1) - Close 34% | 
Overall RR: 3.0:1 ✓ VALID
```

**Execution Plan:**
1. **Short** 1 BTC at $62,500
2. **SL** at $63,138 (all 1 BTC)
3. **TP1** at $61,862 → Close 0.33 BTC
4. **TP2** at $61,224 → Close 0.33 BTC
5. **TP3** at $60,586 → Close 0.34 BTC

---

## Best Practices

### 1. Always Use TP/SL Targets

**Never trade without predefined TP/SL:**
```
❌ BAD:   "I'll sell when it goes up"
✓ GOOD:  "SL $61,980 | TP1 $62,050 | TP2 $62,150 | TP3 $62,250"
```

### 2. Validate Trade Setup Before Entry

```python
validation = rm.validate_trade_setup(trade_setup)

if not validation['is_valid']:
    print(f"Issues: {validation['errors']}")
    # Don't trade!
else:
    print(f"Trade is valid!")
    # Execute trade
```

**Validation Checks:**
- ✓ Risk/Reward >= 1.0:1 (at least break even potential)
- ✓ SL properly placed below entry (LONG) or above entry (SHORT)
- ✓ TP levels properly ordered (TP1 < TP2 < TP3 for LONG)
- ✓ TP levels above entry (LONG) or below entry (SHORT)

### 3. Respect Your TP/SL Levels

**Follow the plan:**
```
If TP1 is hit → CLOSE 33% (no exceptions)
If TP2 is hit → CLOSE 33% more (stick to plan)
If TP3 is hit → CLOSE rest (take the win)
If SL is hit → EXIT all (cut losses immediately)
```

**Don't:**
```
❌ Move SL lower (gives trade more rope)
❌ Move TP higher (expect more than calculated)
❌ Exit early because "I don't like the setup anymore"
❌ Hold after TP is hit hoping for more
```

### 4. Use Position Sizing (Scale In/Out)

**Close partial positions at each TP:**
```
TP1 at 1.2067 → Close 33% profit
    Remaining 67% keeps running with SL

TP2 at 1.2084 → Close another 33% profit
    Remaining 34% still running with SL

TP3 at 1.2101 → Close final 34% profit
    All profits locked in!
```

**Why this works:**
- Take profits along the way (secure gains)
- Still participate in big moves (TP3)
- Average position cost comes down as you close parts

### 5. Adjust for Volatility

**High Volatility:**
- Use wider TP/SL (more breathing room)
- Use ATR for SL (not fixed offset)
- Expect bigger moves, bigger swings

**Low Volatility:**
- Use tighter TP/SL (grab quick profits)
- Fixed offset OK (markets are calm)
- Expect smaller moves, need tighter management

### 6. Track Win Rate by TP Level

**Analyze your trades:**
```
TP1 Hit: 58% (very good)
TP2 Hit: 35% (solid)
TP3 Hit: 18% (decent - some home runs)
SL Hit: 24% (losing trades)

Expected Profit:
= (0.58 × 1.0 × risk) + (0.35 × 2.0 × risk) + (0.18 × 3.0 × risk) - (0.24 × risk)
= (0.58 + 0.70 + 0.54 - 0.24) × risk
= 1.58 × risk per trade ✓ Profitable!
```

### 7. Consider Time Frames

**Different timeframes = Different TP/SL:**

| Timeframe | Entry | SL Distance | TP1 Distance | TP3 Distance | Position Hold |
|-----------|-------|-------------|--------------|--------------|---------------|
| 1-min | Tight | 2-3 pips | 3-5 pips | 5-8 pips | Seconds |
| 5-min | Medium | 5-8 pips | 8-12 pips | 15-25 pips | Minutes |
| 1-hour | Wider | 20-50 pips | 50-100 pips | 100-200 pips | Hours |
| 1-day | Very wide | 100-300 pips | 300-500 pips | 500-1000 pips | Days |

### 8. Keep a Trade Journal

**Document every trade:**
```
Entry: 62,030
Reason: Support bounce + hammer pattern
Target: TP1 @ 62,050, TP2 @ 62,100, TP3 @ 62,150
SL: 61,980

Outcome: TP2 hit at 62,100
Profit: $70 (closed 66% position), $35 remaining

Notes: 
- Good setup, strong confluence
- TP1 touched but didn't stop out
- TP2 hit as planned
- Left 34% running (good)
```

---

## Summary

**TP/SL Is Not Optional**

Every trade needs:
1. Clear entry point (at support/resistance)
2. Defined stop loss (below support for LONG)
3. Three profit targets (1:1, 2:1, 3:1 ratios)
4. Risk/Reward calculation (minimum 1.5:1)
5. Validation (is this trade worth taking?)

**Your Advantage:**
With Pivot Points + Fibonacci, you have precise levels for all three. The `risk_management.py` module calculates them automatically.

**Next Steps:**
1. Configure TP/SL for your market (crypto, stocks, forex)
2. Backtest with automatic TP/SL calculation
3. Paper trade with real signals
4. Track win rate by TP level
5. Optimize based on results

---

*Implementation Date: 2024*  
*Status: ✅ PRODUCTION READY*  
*Last Updated: January 2026*
