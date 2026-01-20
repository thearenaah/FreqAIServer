# TP/SL Quick Reference

## 🎯 Core Concepts

### Entry Points
- **LONG**: At support (EMA 50/200, Pivot S1/S2/S3, Fib retracement)
- **SHORT**: At resistance (EMA 50/200, Pivot R1/R2/R3, Fib retracement)

### Stop Loss Rules
- **LONG**: SL = Support × (1 - 0.5%) = Support - 0.5%
- **SHORT**: SL = Resistance × (1 + 0.5%) = Resistance + 0.5%

### Take Profit Levels
- **TP1**: Entry + (Risk × 1.0) — 1:1 ratio
- **TP2**: Entry + (Risk × 2.0) — 2:1 ratio
- **TP3**: Entry + (Risk × 3.0) — 3:1 ratio

---

## 📊 Example Setup (LONG)

```
Entry:  1.2050  ← At support (Pivot S1)
SL:     1.2030  ← 0.5% below support
Risk:   0.0020  ← Entry - SL

TP1:    1.2070  ← Entry + (0.0020 × 1.0)
TP2:    1.2090  ← Entry + (0.0020 × 2.0)
TP3:    1.2110  ← Entry + (0.0020 × 3.0)

RR:     3.0:1   ← Very good!
```

## 📊 Example Setup (SHORT)

```
Entry:  1.2070  ← At resistance (Pivot R1)
SL:     1.2090  ← 0.5% above resistance
Risk:   0.0020  ← SL - Entry

TP1:    1.2050  ← Entry - (0.0020 × 1.0)
TP2:    1.2030  ← Entry - (0.0020 × 2.0)
TP3:    1.2010  ← Entry - (0.0020 × 3.0)

RR:     3.0:1   ← Very good!
```

---

## 💻 Code Usage

### Calculate LONG Trade

```python
from risk_management import RiskManagement

rm = RiskManagement()

trade = rm.calculate_long_trade_levels(
    entry_price=62030,
    support_level=62000,
    pivot_data={'r1': 62050, 'r2': 62100, 'r3': 62150,
                's1': 62000, 's2': 61950, 's3': 61900},
    fibonacci_data={'0.382': 62020, '0.618': 61980, '1.618': 62150},
    atr=100,
    highest_recent=63200
)

# Access results
print(f"Entry: ${trade['entry']:.2f}")
print(f"SL: ${trade['stop_loss']:.2f}")
print(f"TP1: ${trade['tp1']['price']:.2f}")
print(f"TP2: ${trade['tp2']['price']:.2f}")
print(f"TP3: ${trade['tp3']['price']:.2f}")
print(f"R/R: {trade['risk_reward_ratio']:.2f}:1")
```

### Calculate SHORT Trade

```python
trade = rm.calculate_short_trade_levels(
    entry_price=62070,
    resistance_level=62100,
    pivot_data={'r1': 62100, 'r2': 62150, 'r3': 62200,
                's1': 62000, 's2': 61950, 's3': 61900},
    fibonacci_data={'0.382': 62020, '0.618': 61980},
    atr=100,
    lowest_recent=61800
)

print(f"Entry: ${trade['entry']:.2f}")
print(f"SL: ${trade['stop_loss']:.2f}")
print(f"TP1: ${trade['tp1']['price']:.2f}")
print(f"Risk/Reward: {trade['risk_reward_ratio']:.2f}:1")
```

### Validate Trade

```python
validation = rm.validate_trade_setup(trade)

if validation['is_valid']:
    print("✓ Trade setup is valid!")
else:
    print(f"✗ Errors: {validation['errors']}")
    print(f"⚠ Warnings: {validation['warnings']}")
```

---

## ⚙️ Configuration

### High Volatility Market

```python
from risk_management import RiskManagement, RiskManagementConfig

config = RiskManagementConfig(
    tp1_risk_reward=1.2,
    tp2_risk_reward=2.5,
    tp3_risk_reward=4.0,
    atr_multiplier=2.0,
    tp1_size=0.25,
    tp2_size=0.25,
    tp3_size=0.50,
)
rm = RiskManagement(config)
```

### Low Volatility Market

```python
config = RiskManagementConfig(
    tp1_risk_reward=0.8,
    tp2_risk_reward=1.5,
    tp3_risk_reward=2.0,
    atr_multiplier=1.0,
    tp1_size=0.50,
    tp2_size=0.35,
    tp3_size=0.15,
)
rm = RiskManagement(config)
```

### Conservative Trading

```python
config = RiskManagementConfig(
    tp1_risk_reward=0.5,
    tp2_risk_reward=1.0,
    tp3_risk_reward=1.5,
    sl_support_offset=0.002,
    atr_multiplier=0.5,
    tp1_size=0.67,
    tp2_size=0.25,
    tp3_size=0.08,
)
rm = RiskManagement(config)
```

---

## 📈 Position Sizing at TP Levels

| TP Level | When Hit | Close | Remaining | Running SL |
|----------|----------|-------|-----------|-----------|
| Entry | Start | 100% | — | Below Entry |
| TP1 (1:1) | Profit | 33% | 67% | Entry or Breakeven |
| TP2 (2:1) | More profit | 33% | 34% | TP1 or Breakeven |
| TP3 (3:1) | Big profit | 34% | 0% | All closed, profit locked |

---

## 🎯 Hit Rate Expectations

| TP Level | Expected Hit Rate | Expected Profit |
|----------|------------------|-----------------|
| TP1 (1:1) | 60%+ | Very consistent |
| TP2 (2:1) | 35-40% | Good rewards |
| TP3 (3:1) | 18-25% | Home run trades |
| SL Hit | 20-25% | Controlled losses |

**Overall:** 60% TP1 + 35% TP2 + 20% TP3 = Strong profitability

---

## 🔧 Integration with Strategy

### In strategy_rules.py

```python
# Automatic TP/SL when signal is generated
engine = StrategyEngine(rules)

# Check signal
signal, confidence, reasons = engine.check_long_signal(...)

# If LONG signal, calculate TP/SL
if signal == Signal.LONG:
    tp_sl = engine.calculate_long_tp_sl(
        entry_price=price,
        support_level=support,
        pivot_data=pivot_data,
        fibonacci_data=fib_data,
        atr=atr
    )
    # Trade setup ready!
```

### In features.py

```python
# Signal output now includes TP/SL
features['signal_analysis'] = {
    'long_signal': 'buy',
    'long_confidence': 0.78,
    'long_tp_sl': {
        'entry': 62030,
        'stop_loss': 61980,
        'tp1': {'price': 62050, 'risk_reward': 1.0},
        'tp2': {'price': 62070, 'risk_reward': 2.0},
        'tp3': {'price': 62090, 'risk_reward': 3.0},
    }
}
```

---

## ✅ Pre-Trade Checklist

- [ ] Entry at support/resistance (not random price)
- [ ] SL below support (LONG) or above resistance (SHORT)
- [ ] Risk/Reward >= 1.5:1
- [ ] TP1 > Entry (LONG) or TP1 < Entry (SHORT)
- [ ] TP2 > TP1 (LONG) or TP2 < TP1 (SHORT)
- [ ] TP3 > TP2 (LONG) or TP3 < TP2 (SHORT)
- [ ] Validation shows ✓ VALID
- [ ] Pattern confirmation present
- [ ] Confluence at entry (2+ levels)
- [ ] Ready to execute!

---

## 🚫 Common Mistakes

❌ **Trading without TP/SL**
→ Result: No plan, emotional trading

❌ **SL too tight**
→ Result: Stopped out constantly by noise

❌ **SL too wide**
→ Result: Too much risk, big losses

❌ **Moving SL after entry**
→ Result: Discipline breakdown, bigger losses

❌ **Moving TP higher after hit**
→ Result: Greed, leaving with less profit

❌ **Not closing at TP1/TP2**
→ Result: Missing easy gains, hoping for more

❌ **Risk/Reward < 1.0:1**
→ Result: Need 60%+ win rate just to break even

---

## ✓ Best Practices

✓ **Always use TP/SL before entering**
→ Have plan, execute plan

✓ **SL should be logical (below support)**
→ Placement makes sense

✓ **Close positions at TP levels**
→ Lock in profits systematically

✓ **Use partial closing**
→ Secure gains while participating in big moves

✓ **Track win rate by TP level**
→ Know your edge (TP1? TP2? TP3?)

✓ **Validate trade setup**
→ Only take high-quality setups

✓ **Adjust for volatility**
→ Markets aren't always the same

✓ **Keep a journal**
→ Learn from each trade

---

## 📞 API Reference

### RiskManagement Class

```python
class RiskManagement:
    def __init__(self, config: RiskManagementConfig = None)
    
    def calculate_long_trade_levels(
        entry_price: float,
        support_level: float,
        pivot_data: Dict = None,
        fibonacci_data: Dict = None,
        atr: float = None,
        highest_recent_price: float = None,
    ) -> Dict
    
    def calculate_short_trade_levels(
        entry_price: float,
        resistance_level: float,
        pivot_data: Dict = None,
        fibonacci_data: Dict = None,
        atr: float = None,
        lowest_recent_price: float = None,
    ) -> Dict
    
    def validate_trade_setup(trade_setup: Dict) -> Dict
    
    def adjust_tp_for_volatility(
        base_tp: float,
        atr: float,
        volatility_level: str,
        direction: str,
    ) -> float
```

### Return Value Structure

```python
trade_setup = {
    'direction': 'LONG',                    # Trade direction
    'entry': 62030.0,                       # Entry price
    'support_level': 62000.0,               # Support (for LONG)
    'stop_loss': 61980.0,                   # SL price
    'sl_reason': '0.5% below support',
    'risk': 50.0,                           # Risk amount
    
    'tp1': {                                # Take Profit 1
        'price': 62080.0,
        'source': 'Pivot R1',
        'risk_reward': 1.0,
        'position_size': 0.33,
        'profit': 50.0,
    },
    
    'tp2': {                                # Take Profit 2
        'price': 62130.0,
        'source': 'Pivot R2',
        'risk_reward': 2.0,
        'position_size': 0.33,
        'profit': 100.0,
    },
    
    'tp3': {                                # Take Profit 3
        'price': 62180.0,
        'source': 'Fibonacci 261.8%',
        'risk_reward': 3.0,
        'position_size': 0.34,
        'profit': 150.0,
    },
    
    'risk_reward_ratio': 3.0,               # Overall R/R
    'trade_description': '...',             # Human-readable summary
    'validation': {                         # Validation results
        'is_valid': True,
        'warnings': [],
        'errors': []
    }
}
```

---

## 📚 Further Reading

- See `RISK_MANAGEMENT_GUIDE.md` for detailed explanation
- See `STRATEGY_IMPLEMENTATION.md` for overall strategy
- See `FIBONACCI_GUIDE.md` for Fibonacci extension levels
- See `STRATEGY_QUICK_REFERENCE.md` for strategy overview

---

*Quick Reference v1.0*  
*Status: ✅ PRODUCTION READY*  
*Last Updated: January 2026*
