"""
Regime Classifier - TheArena FreqAI Server
==========================================
Classifies market into one of 4 regimes:
  0 = STRONG_TREND_UP
  1 = STRONG_TREND_DOWN
  2 = WEAK_TREND
  3 = RANGING / CHOPPY

Two usage modes:
  A) Rule-based (instant, no training required) — used for signal filtering
  B) ML-based (XGBoost trained on labelled regime data) — used as meta-feature

The rule-based classifier is always available.
The ML classifier is trained once per symbol/timeframe and cached.

Author: TheArena Platform
"""

import numpy as np
import pandas as pd
import joblib
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Regime labels
# ─────────────────────────────────────────────

REGIME_STRONG_UP   = 0
REGIME_STRONG_DOWN = 1
REGIME_WEAK_TREND  = 2
REGIME_RANGING     = 3

REGIME_NAMES = {
    REGIME_STRONG_UP:   'STRONG_TREND_UP',
    REGIME_STRONG_DOWN: 'STRONG_TREND_DOWN',
    REGIME_WEAK_TREND:  'WEAK_TREND',
    REGIME_RANGING:     'RANGING',
}


# ─────────────────────────────────────────────
#  Rule-based classifier (always available)
# ─────────────────────────────────────────────

@dataclass
class RegimeResult:
    regime: int
    regime_name: str
    adx: float
    choppiness: float
    trend_direction: int   # +1 bull, -1 bear, 0 neutral
    confidence: float      # 0-1 how confident the rule-based call is
    allow_long: bool
    allow_short: bool
    notes: str


def classify_regime_rules(features: Dict[str, float]) -> RegimeResult:
    """
    Fast rule-based regime detection from precomputed features.
    Call this every time before routing to trend or range model.

    Decision logic
    ──────────────
    ADX > 40  AND chop < 0.42  → STRONG_TREND (up or down by pdi/mdi)
    ADX > 25  AND chop < 0.50  → WEAK_TREND
    ADX < 20  OR  chop > 0.62  → RANGING
    else                        → WEAK_TREND
    """
    adx  = features.get('adx', 0.2) * 100   # stored as 0-1
    chop = features.get('choppiness', 0.5) * 100
    pdi_above = bool(features.get('pdi_above_mdi', 0))
    price_ext_up   = bool(features.get('price_extended_up', 0))
    price_ext_down = bool(features.get('price_extended_down', 0))
    zscore = features.get('zscore_50', 0.0)

    # Direction
    trend_dir = 1 if pdi_above else -1

    # Regime
    if adx >= 40 and chop <= 42:
        regime = REGIME_STRONG_UP if pdi_above else REGIME_STRONG_DOWN
        confidence = min(1.0, (adx - 40) / 30 + (42 - chop) / 40)
    elif adx >= 25 and chop <= 50:
        regime = REGIME_WEAK_TREND
        confidence = min(0.75, (adx - 25) / 30)
    elif adx <= 20 or chop >= 62:
        regime = REGIME_RANGING
        confidence = min(1.0, max((chop - 62) / 30, (20 - adx) / 20))
        trend_dir = 0
    else:
        regime = REGIME_WEAK_TREND
        confidence = 0.4

    # Signal permissions
    # Don't go LONG if price is already extended upward (overextended = higher SL risk)
    # Don't go SHORT if price is already extended downward
    allow_long  = not price_ext_up
    allow_short = not price_ext_down

    # In ranging markets both directions are fine (mean-reversion)
    if regime == REGIME_RANGING:
        allow_long  = True
        allow_short = True

    notes_parts = []
    if price_ext_up:   notes_parts.append("price_overextended_up")
    if price_ext_down: notes_parts.append("price_overextended_down")
    if abs(zscore) > 3: notes_parts.append(f"zscore={zscore:.1f}")

    return RegimeResult(
        regime=regime,
        regime_name=REGIME_NAMES[regime],
        adx=adx,
        choppiness=chop,
        trend_direction=trend_dir,
        confidence=round(confidence, 3),
        allow_long=allow_long,
        allow_short=allow_short,
        notes=', '.join(notes_parts) if notes_parts else 'ok',
    )


# ─────────────────────────────────────────────
#  Signal routing / filtering
# ─────────────────────────────────────────────

def should_emit_signal(
    signal: str,          # 'BUY' or 'SELL'
    confidence: float,
    features: Dict[str, float],
    timeframe: str,
    min_confidence: float = 0.62,
) -> Tuple[bool, str]:
    """
    Gate a signal through regime + confidence filters.

    Returns:
        (allowed: bool, reason: str)
    """
    if confidence < min_confidence:
        return False, f"confidence {confidence:.2f} < {min_confidence}"

    regime = classify_regime_rules(features)

    # Hard block: weekend / no session (passed from task context)
    # (handled at the Celery task level, not here)

    # Hard block: trading against a strong trend
    if regime.regime == REGIME_STRONG_UP and signal == 'SELL':
        # Only allow sells if price is significantly overextended
        if not features.get('price_extended_up', 0):
            return False, f"SELL blocked in STRONG_TREND_UP (ADX={regime.adx:.0f})"

    if regime.regime == REGIME_STRONG_DOWN and signal == 'BUY':
        if not features.get('price_extended_down', 0):
            return False, f"BUY blocked in STRONG_TREND_DOWN (ADX={regime.adx:.0f})"

    # Block when not allowed by regime
    if signal == 'BUY'  and not regime.allow_long:
        return False, f"long not allowed: {regime.notes}"
    if signal == 'SELL' and not regime.allow_short:
        return False, f"short not allowed: {regime.notes}"

    # Require MTF alignment for SHORT timeframes (5m/15m/30m)
    if timeframe in ('5m', '15m', '30m'):
        if signal == 'BUY'  and features.get('mtf_confluence_bear', 0):
            return False, "short-TF BUY conflicts with HTF bearish confluence"
        if signal == 'SELL' and features.get('mtf_confluence_bull', 0):
            return False, "short-TF SELL conflicts with HTF bullish confluence"

    return True, f"ok (regime={regime.regime_name}, ADX={regime.adx:.0f}, conf={confidence:.2f})"


# ─────────────────────────────────────────────
#  ATR-based TP / SL calculator
# ─────────────────────────────────────────────

def calculate_tp_sl(
    signal: str,
    entry_price: float,
    atr: float,
    regime: Optional[RegimeResult] = None,
) -> Dict[str, float]:
    """
    Calculate TP1/TP2/TP3 and SL using ATR multiples.
    Regime-aware: wider targets in trending markets, tighter in ranging.

    Returns dict with: stop_loss, take_profit_1, take_profit_2, take_profit_3
    """
    if atr is None or atr <= 0:
        # fallback: 1% of price per level
        atr = entry_price * 0.01

    # Adjust multipliers by regime
    if regime and regime.regime in (REGIME_STRONG_UP, REGIME_STRONG_DOWN):
        sl_mult  = 1.5
        tp1_mult = 2.0
        tp2_mult = 4.0
        tp3_mult = 6.0
    elif regime and regime.regime == REGIME_RANGING:
        # Tighter targets in range
        sl_mult  = 1.0
        tp1_mult = 1.0
        tp2_mult = 1.8
        tp3_mult = 2.5
    else:
        sl_mult  = 1.5
        tp1_mult = 1.5
        tp2_mult = 3.0
        tp3_mult = 4.5

    sl_dist  = atr * sl_mult
    tp1_dist = atr * tp1_mult
    tp2_dist = atr * tp2_mult
    tp3_dist = atr * tp3_mult

    if signal.upper() == 'BUY':
        return {
            'stop_loss':     round(entry_price - sl_dist,  8),
            'take_profit_1': round(entry_price + tp1_dist, 8),
            'take_profit_2': round(entry_price + tp2_dist, 8),
            'take_profit_3': round(entry_price + tp3_dist, 8),
        }
    else:  # SELL
        return {
            'stop_loss':     round(entry_price + sl_dist,  8),
            'take_profit_1': round(entry_price - tp1_dist, 8),
            'take_profit_2': round(entry_price - tp2_dist, 8),
            'take_profit_3': round(entry_price - tp3_dist, 8),
        }
