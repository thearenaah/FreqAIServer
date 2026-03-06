"""
Feature Engineering - TheArena FreqAI Server
============================================
Architecture:
  - Single-timeframe features (55+) used per model
  - Market regime detection (trending vs ranging)
  - Session/time-of-day features (critical for forex)
  - ADX, Z-score, Choppiness Index for regime classification
  - Proper ATR calculation (no lookahead)

Author: TheArena Platform
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _wilder_smooth(series: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (used for ADX, ATR)"""
    result = np.zeros(len(series))
    if len(series) < period:
        return result
    result[period - 1] = np.mean(series[:period])
    for i in range(period, len(series)):
        result[i] = (result[i - 1] * (period - 1) + series[i]) / period
    return result


def _safe_div(a, b, default=0.0):
    if b == 0 or (isinstance(b, float) and np.isnan(b)):
        return default
    return a / b


# ─────────────────────────────────────────────
#  FeatureEngineer
# ─────────────────────────────────────────────

class FeatureEngineer:
    """
    Calculates all ML features used by the regime classifier and
    per-timeframe directional models.
    """

    # ── Low-level indicators ──────────────────

    @staticmethod
    def calculate_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = _wilder_smooth(gain, period)
        avg_loss = _wilder_smooth(loss, period)
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        # Pad back to original length
        return np.concatenate([[50.0], rsi])

    @staticmethod
    def calculate_atr(high: np.ndarray, low: np.ndarray,
                      close: np.ndarray, period: int = 14) -> np.ndarray:
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = _wilder_smooth(tr, period)
        return np.concatenate([[np.nan], atr])

    @staticmethod
    def calculate_adx(high: np.ndarray, low: np.ndarray,
                      close: np.ndarray, period: int = 14) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (ADX, +DI, -DI) arrays same length as input"""
        n = len(high)
        plus_dm  = np.zeros(n)
        minus_dm = np.zeros(n)
        tr_arr   = np.zeros(n)

        for i in range(1, n):
            up   = high[i]  - high[i - 1]
            down = low[i - 1] - low[i]
            plus_dm[i]  = up   if (up > down and up > 0)   else 0.0
            minus_dm[i] = down if (down > up and down > 0) else 0.0
            tr_arr[i] = max(high[i] - low[i],
                            abs(high[i] - close[i - 1]),
                            abs(low[i]  - close[i - 1]))

        s_tr  = _wilder_smooth(tr_arr[1:],  period)
        s_pdm = _wilder_smooth(plus_dm[1:], period)
        s_mdm = _wilder_smooth(minus_dm[1:],period)

        pdi = 100 * s_pdm / (s_tr + 1e-10)
        mdi = 100 * s_mdm / (s_tr + 1e-10)
        dx  = 100 * np.abs(pdi - mdi) / (pdi + mdi + 1e-10)
        adx = _wilder_smooth(dx, period)

        # Pad back to original length
        pad = np.full(1, np.nan)
        return (np.concatenate([pad, adx]),
                np.concatenate([pad, pdi]),
                np.concatenate([pad, mdi]))

    @staticmethod
    def calculate_macd(close: np.ndarray):
        ema12 = pd.Series(close).ewm(span=12, adjust=False).mean().values
        ema26 = pd.Series(close).ewm(span=26, adjust=False).mean().values
        macd  = ema12 - ema26
        signal = pd.Series(macd).ewm(span=9, adjust=False).mean().values
        hist   = macd - signal
        return macd, signal, hist

    # ── Main feature builder ──────────────────

    @staticmethod
    def calculate_advanced_features(df: pd.DataFrame,
                                    timestamp: Optional[pd.Timestamp] = None) -> Dict[str, float]:
        """
        Calculate 65+ features for the ML model.

        Args:
            df        : DataFrame with columns [open, high, low, close, volume, timestamp(optional)]
            timestamp : Explicit timestamp for session features (uses df index or 'timestamp' col if None)

        Returns:
            Flat dict of float features (no NaN, no Inf)
        """
        close  = df['close'].values.astype(float)
        high   = df['high'].values.astype(float)
        low    = df['low'].values.astype(float)
        volume = df['volume'].values.astype(float)
        open_  = df['open'].values.astype(float)

        features: Dict[str, float] = {}
        cp = close[-1]   # current price

        # ── 1. TREND STRENGTH (8) ──────────────────────────────────────────
        sma_20  = pd.Series(close).rolling(20).mean().values
        sma_50  = pd.Series(close).rolling(50).mean().values
        sma_200 = pd.Series(close).rolling(200).mean().values

        features['trend_sma20_above_50']    = 1.0 if sma_20[-1]  > sma_50[-1]  else 0.0
        features['trend_sma50_above_200']   = 1.0 if sma_50[-1]  > sma_200[-1] else 0.0
        features['trend_price_above_sma20'] = 1.0 if cp > sma_20[-1]  else 0.0
        features['trend_price_above_sma50'] = 1.0 if cp > sma_50[-1]  else 0.0
        features['uptrend_strength']   = 1.0 if (sma_20[-1] > sma_50[-1] > sma_200[-1]) else (0.5 if sma_20[-1] > sma_50[-1] else 0.0)
        features['downtrend_strength'] = 1.0 if (sma_20[-1] < sma_50[-1] < sma_200[-1]) else (0.5 if sma_20[-1] < sma_50[-1] else 0.0)

        slope_20 = _safe_div(sma_20[-1] - sma_20[-min(20, len(sma_20))], sma_20[-min(20, len(sma_20))] + 1e-10)
        slope_50 = _safe_div(sma_50[-1] - sma_50[-min(50, len(sma_50))], sma_50[-min(50, len(sma_50))] + 1e-10)
        features['trend_slope_20'] = float(np.clip(slope_20, -0.5, 0.5))
        features['trend_slope_50'] = float(np.clip(slope_50, -0.5, 0.5))

        # ── 2. ADX / REGIME (7) ───────────────────────────────────────────
        adx_arr, pdi_arr, mdi_arr = FeatureEngineer.calculate_adx(high, low, close, 14)
        adx_val = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 20.0
        pdi_val = float(pdi_arr[-1]) if not np.isnan(pdi_arr[-1]) else 20.0
        mdi_val = float(mdi_arr[-1]) if not np.isnan(mdi_arr[-1]) else 20.0

        features['adx']            = adx_val / 100.0
        features['adx_trending']   = 1.0 if adx_val > 25 else 0.0
        features['adx_strong']     = 1.0 if adx_val > 40 else 0.0
        features['pdi_above_mdi']  = 1.0 if pdi_val > mdi_val else 0.0
        features['adx_rising']     = 1.0 if (len(adx_arr) > 5 and adx_arr[-1] > adx_arr[-5]) else 0.0

        # Choppiness Index (0=pure trend, 100=pure range; threshold 61.8)
        n_chop = min(14, len(close) - 1)
        atr_sum = sum(
            max(high[-i] - low[-i],
                abs(high[-i] - close[-(i + 1)]),
                abs(low[-i]  - close[-(i + 1)]))
            for i in range(1, n_chop + 1)
        )
        total_range = max(high[-n_chop:]) - min(low[-n_chop:])
        chop = 100 * np.log10(_safe_div(atr_sum, total_range + 1e-10, 1.0)) / np.log10(n_chop) if n_chop > 1 else 50.0
        features['choppiness']    = float(np.clip(chop, 0, 100)) / 100.0
        features['market_ranging'] = 1.0 if chop > 61.8 else 0.0

        # ── 3. MOMENTUM (8) ───────────────────────────────────────────────
        rsi_arr = FeatureEngineer.calculate_rsi(close, 14)
        rsi_val = float(rsi_arr[-1])
        macd, sig, hist = FeatureEngineer.calculate_macd(close)

        features['momentum_rsi']            = rsi_val / 100.0
        features['momentum_rsi_overbought'] = 1.0 if rsi_val > 70 else 0.0
        features['momentum_rsi_oversold']   = 1.0 if rsi_val < 30 else 0.0
        features['momentum_macd_positive']  = 1.0 if macd[-1] > sig[-1] else 0.0
        hist_std = float(np.std(hist)) if len(hist) > 1 else 1.0
        features['momentum_macd_histogram'] = float(np.clip(_safe_div(hist[-1], hist_std + 1e-10), -5, 5))
        features['momentum_macd_strength']  = float(np.clip(abs(macd[-1] - sig[-1]) / (abs(np.mean(np.abs(hist))) + 1e-10), 0, 10))
        features['momentum_divergence']  = 1.0 if (rsi_val > 50 and cp < close[-10]) else 0.0
        features['momentum_convergence'] = 1.0 if (rsi_val > 50 and cp > close[-10]) else 0.0

        # ── 4. VOLATILITY (8) ─────────────────────────────────────────────
        atr_arr = FeatureEngineer.calculate_atr(high, low, close, 14)
        atr_val = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else (cp * 0.01)
        atr_sma  = float(np.nanmean(atr_arr[-14:])) if len(atr_arr) >= 14 else atr_val
        returns  = np.diff(close) / (close[:-1] + 1e-10)

        features['volatility_atr']        = _safe_div(atr_val, cp)
        features['volatility_high']       = 1.0 if atr_val > atr_sma * 1.2 else 0.0
        features['volatility_low']        = 1.0 if atr_val < atr_sma * 0.8 else 0.0
        features['volatility_expanding']  = 1.0 if atr_val > float(np.nanmean(atr_arr[-20:-1])) else 0.0
        features['volatility_std']        = float(np.std(returns[-20:])) if len(returns) >= 20 else 0.0
        features['volatility_regime_high']= 1.0 if (len(returns) > 20 and np.std(returns[-20:]) > np.std(returns) * 1.1) else 0.0
        features['volatility_compression']= 1.0 if atr_val < atr_sma * 0.7 else 0.0

        # Z-score: how extended is price from its 50-period mean?
        std_50 = float(pd.Series(close).rolling(50).std().iloc[-1]) or 1e-10
        zscore = _safe_div(cp - sma_50[-1], std_50)
        features['zscore_50']             = float(np.clip(zscore, -5, 5))
        features['price_extended_up']     = 1.0 if zscore >  2.0 else 0.0
        features['price_extended_down']   = 1.0 if zscore < -2.0 else 0.0

        # ── 5. VOLUME (7) ─────────────────────────────────────────────────
        vol_sma_20 = float(np.mean(volume[-20:])) if len(volume) >= 20 else float(np.mean(volume))
        vol_sma_50 = float(np.mean(volume[-50:])) if len(volume) >= 50 else vol_sma_20

        features['volume_ratio']       = _safe_div(volume[-1], vol_sma_20 + 1e-10, 1.0)
        features['volume_above_avg']   = 1.0 if volume[-1] > vol_sma_20 else 0.0
        features['volume_confirmation']= 1.0 if (volume[-1] > vol_sma_20 and close[-1] > close[-2]) else 0.0
        features['volume_divergence']  = 1.0 if (volume[-1] < vol_sma_20 and close[-1] > close[-2]) else 0.0
        features['volume_climax']      = 1.0 if (len(volume) >= 20 and volume[-1] > np.percentile(volume[-20:], 90)) else 0.0
        features['volume_drying_up']   = 1.0 if (len(volume) >= 20 and volume[-1] < np.percentile(volume[-20:], 20)) else 0.0
        features['volume_trend']       = 1.0 if vol_sma_20 > vol_sma_50 else 0.0

        # ── 6. SUPPORT / RESISTANCE (6) ───────────────────────────────────
        recent_high = float(np.max(high[-20:])) if len(high) >= 20 else float(np.max(high))
        recent_low  = float(np.min(low[-20:]))  if len(low)  >= 20 else float(np.min(low))
        recent_range = recent_high - recent_low + 1e-10

        features['resistance_nearness'] = _safe_div(recent_high - cp, recent_range, 0.5)
        features['support_nearness']    = _safe_div(cp - recent_low,  recent_range, 0.5)
        features['at_resistance']       = 1.0 if _safe_div(recent_high - cp, recent_range) < 0.05 else 0.0
        features['at_support']          = 1.0 if _safe_div(cp - recent_low,  recent_range) < 0.05 else 0.0
        features['breakout_resistance'] = 1.0 if cp > recent_high else 0.0
        features['breakout_support']    = 1.0 if cp < recent_low  else 0.0

        # ── 7. MARKET STRUCTURE (5) ───────────────────────────────────────
        features['higher_lows']  = 1.0 if (len(low)  >= 11 and low[-1]  > low[-5]  > low[-10])  else 0.0
        features['lower_highs']  = 1.0 if (len(high) >= 11 and high[-1] < high[-5] < high[-10]) else 0.0
        features['higher_highs'] = 1.0 if (len(high) >= 11 and high[-1] > high[-5] > high[-10]) else 0.0
        features['lower_lows']   = 1.0 if (len(low)  >= 11 and low[-1]  < low[-5]  < low[-10])  else 0.0
        features['inside_bar']   = 1.0 if (high[-1] < high[-2] and low[-1] > low[-2]) else 0.0

        # ── 8. CANDLE PATTERNS (5) ────────────────────────────────────────
        body  = abs(close[-1] - open_[-1])
        c_range = high[-1] - low[-1] + 1e-10
        upper_wick = high[-1] - max(close[-1], open_[-1])
        lower_wick = min(close[-1], open_[-1]) - low[-1]

        features['candle_bullish']       = 1.0 if close[-1] > open_[-1] else 0.0
        features['candle_hammer']        = 1.0 if (lower_wick > c_range * 0.6 and upper_wick < c_range * 0.2) else 0.0
        features['candle_shooting_star'] = 1.0 if (upper_wick > c_range * 0.6 and lower_wick < c_range * 0.2) else 0.0
        features['candle_doji']          = 1.0 if body < c_range * 0.1 else 0.0
        features['candle_engulfing_bull']= 1.0 if (len(close) >= 2 and close[-1] > open_[-1] and
                                                    close[-1] > open_[-2] and open_[-1] < close[-2]) else 0.0

        # ── 9. PRICE ACTION (4) ───────────────────────────────────────────
        features['price_above_open'] = 1.0 if close[-1] > open_[-1] else 0.0
        features['price_momentum']   = float(np.clip(_safe_div(cp - close[-5], close[-5] + 1e-10), -0.5, 0.5)) if len(close) > 5 else 0.0
        features['consecutive_ups']  = float(sum(1 for i in range(1, min(5, len(close))) if close[-i] > close[-(i + 1)]))
        features['consecutive_downs']= float(sum(1 for i in range(1, min(5, len(close))) if close[-i] < close[-(i + 1)]))

        # ── 10. MEAN REVERSION / BOLLINGER (5) ───────────────────────────
        bb_mid = float(pd.Series(close).rolling(20).mean().iloc[-1])
        bb_std = float(pd.Series(close).rolling(20).std().iloc[-1]) or 1e-10
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_range = bb_upper - bb_lower + 1e-10

        features['bb_position']  = float(np.clip(_safe_div(cp - bb_lower, bb_range, 0.5), 0, 1))
        features['bb_overbought']= 1.0 if cp > bb_upper else 0.0
        features['bb_oversold']  = 1.0 if cp < bb_lower else 0.0
        features['price_sma20_distance'] = float(np.clip(_safe_div(cp - bb_mid, bb_mid + 1e-10), -0.2, 0.2))

        # RSI divergence
        rsi_prev = float(FeatureEngineer.calculate_rsi(close[:-3], 14)[-1]) if len(close) > 17 else rsi_val
        features['bearish_divergence'] = 1.0 if (cp > close[-4] and rsi_val < rsi_prev and rsi_val > 60) else 0.0
        features['bullish_divergence'] = 1.0 if (cp < close[-4] and rsi_val > rsi_prev and rsi_val < 40) else 0.0

        # ── 11. SESSION / TIME FEATURES (8) ──────────────────────────────
        ts = None
        if timestamp is not None:
            ts = pd.Timestamp(timestamp)
        elif 'timestamp' in df.columns:
            ts = pd.Timestamp(df['timestamp'].iloc[-1])
        elif hasattr(df.index[-1], 'hour'):
            ts = df.index[-1]

        if ts is not None:
            try:
                hour = ts.hour
                dow  = ts.dayofweek   # 0=Mon … 6=Sun
                features['hour_sin']          = float(np.sin(2 * np.pi * hour / 24))
                features['hour_cos']          = float(np.cos(2 * np.pi * hour / 24))
                features['day_of_week']       = dow / 4.0
                features['is_london_session'] = 1.0 if  7 <= hour < 17 else 0.0
                features['is_ny_session']     = 1.0 if 13 <= hour < 21 else 0.0
                features['is_asian_session']  = 1.0 if (hour >= 22 or hour < 8) else 0.0
                features['is_overlap']        = 1.0 if 13 <= hour < 17 else 0.0   # London/NY overlap
                features['is_monday']         = 1.0 if dow == 0 else 0.0
                features['is_friday']         = 1.0 if dow == 4 else 0.0
            except Exception:
                for k in ['hour_sin','hour_cos','day_of_week','is_london_session',
                           'is_ny_session','is_asian_session','is_overlap','is_monday','is_friday']:
                    features[k] = 0.0
        else:
            for k in ['hour_sin','hour_cos','day_of_week','is_london_session',
                       'is_ny_session','is_asian_session','is_overlap','is_monday','is_friday']:
                features[k] = 0.0

        # ── Sanitise: no NaN / Inf ─────────────────────────────────────
        clean: Dict[str, float] = {}
        for k, v in features.items():
            try:
                fv = float(v)
                clean[k] = 0.0 if (np.isnan(fv) or np.isinf(fv)) else fv
            except Exception:
                clean[k] = 0.0

        return clean

    # ── Feature column list (must stay in sync with above) ───────────────

    @staticmethod
    def get_feature_columns() -> List[str]:
        return [
            # Trend (8)
            'trend_sma20_above_50','trend_sma50_above_200',
            'trend_price_above_sma20','trend_price_above_sma50',
            'uptrend_strength','downtrend_strength',
            'trend_slope_20','trend_slope_50',
            # ADX / Regime (9)
            'adx','adx_trending','adx_strong','pdi_above_mdi','adx_rising',
            'choppiness','market_ranging',
            'zscore_50','price_extended_up','price_extended_down',
            # Momentum (8)
            'momentum_rsi','momentum_rsi_overbought','momentum_rsi_oversold',
            'momentum_macd_positive','momentum_macd_histogram','momentum_macd_strength',
            'momentum_divergence','momentum_convergence',
            # Volatility (8)
            'volatility_atr','volatility_high','volatility_low',
            'volatility_expanding','volatility_std','volatility_regime_high',
            'volatility_compression',
            # Volume (7)
            'volume_ratio','volume_above_avg','volume_confirmation',
            'volume_divergence','volume_climax','volume_drying_up','volume_trend',
            # Support/Resistance (6)
            'resistance_nearness','support_nearness',
            'at_resistance','at_support','breakout_resistance','breakout_support',
            # Market Structure (5)
            'higher_lows','lower_highs','higher_highs','lower_lows','inside_bar',
            # Candle Patterns (5)
            'candle_bullish','candle_hammer','candle_shooting_star',
            'candle_doji','candle_engulfing_bull',
            # Price Action (4)
            'price_above_open','price_momentum','consecutive_ups','consecutive_downs',
            # Mean Reversion / BB (6)
            'bb_position','bb_overbought','bb_oversold','price_sma20_distance',
            'bearish_divergence','bullish_divergence',
            # Session / Time (9)
            'hour_sin','hour_cos','day_of_week',
            'is_london_session','is_ny_session','is_asian_session',
            'is_overlap','is_monday','is_friday',
        ]


# ─────────────────────────────────────────────
#  Multi-Timeframe Confluence Builder
# ─────────────────────────────────────────────

# Higher timeframe chain used to add context to lower ones
MTF_CHAIN: Dict[str, str] = {
    '5m':  '1h',
    '15m': '1h',
    '30m': '4h',
    '1h':  '4h',
    '4h':  '1d',
    '1d':  '1w',
    '1w':  '1w',   # no higher
}


def build_mtf_features(base_features: Dict[str, float],
                       higher_features: Optional[Dict[str, float]]) -> Dict[str, float]:
    """
    Merge base-timeframe features with higher-timeframe context.
    Higher-TF features are prefixed with 'htf_' and kept as separate
    columns so the model can learn alignment vs divergence.

    If no higher-TF data is available the htf_ columns are filled with
    neutral values so the feature matrix shape stays constant.
    """
    merged = dict(base_features)

    # Keys we want from the higher timeframe
    htf_keys = [
        'trend_sma20_above_50', 'trend_sma50_above_200',
        'uptrend_strength', 'downtrend_strength',
        'adx', 'adx_trending', 'adx_strong', 'pdi_above_mdi',
        'choppiness', 'market_ranging',
        'momentum_rsi', 'momentum_rsi_overbought', 'momentum_rsi_oversold',
        'momentum_macd_positive',
        'bb_position', 'bb_overbought', 'bb_oversold',
        'at_resistance', 'at_support',
        'bearish_divergence', 'bullish_divergence',
        'price_extended_up', 'price_extended_down',
        'zscore_50',
    ]

    if higher_features:
        for k in htf_keys:
            merged[f'htf_{k}'] = higher_features.get(k, 0.0)

        # Alignment signal: base and HTF trend agree
        base_bull = 1.0 if base_features.get('pdi_above_mdi', 0) else 0.0
        htf_bull  = 1.0 if higher_features.get('pdi_above_mdi', 0) else 0.0
        merged['mtf_trend_aligned']  = 1.0 if base_bull == htf_bull else 0.0
        merged['mtf_trend_conflict'] = 1.0 if base_bull != htf_bull else 0.0

        # Confluence: both trending AND aligned
        merged['mtf_confluence_bull'] = (
            1.0 if (base_features.get('adx_trending', 0) and
                    higher_features.get('adx_trending', 0) and
                    base_features.get('pdi_above_mdi', 0) and
                    higher_features.get('pdi_above_mdi', 0))
            else 0.0
        )
        merged['mtf_confluence_bear'] = (
            1.0 if (base_features.get('adx_trending', 0) and
                    higher_features.get('adx_trending', 0) and
                    not base_features.get('pdi_above_mdi', 0) and
                    not higher_features.get('pdi_above_mdi', 0))
            else 0.0
        )
    else:
        for k in htf_keys:
            merged[f'htf_{k}'] = 0.0
        merged['mtf_trend_aligned']   = 0.0
        merged['mtf_trend_conflict']  = 0.0
        merged['mtf_confluence_bull'] = 0.0
        merged['mtf_confluence_bear'] = 0.0

    return merged


def get_mtf_feature_columns(base_columns: List[str]) -> List[str]:
    """Return full column list including MTF additions."""
    htf_keys = [
        'trend_sma20_above_50', 'trend_sma50_above_200',
        'uptrend_strength', 'downtrend_strength',
        'adx', 'adx_trending', 'adx_strong', 'pdi_above_mdi',
        'choppiness', 'market_ranging',
        'momentum_rsi', 'momentum_rsi_overbought', 'momentum_rsi_oversold',
        'momentum_macd_positive',
        'bb_position', 'bb_overbought', 'bb_oversold',
        'at_resistance', 'at_support',
        'bearish_divergence', 'bullish_divergence',
        'price_extended_up', 'price_extended_down',
        'zscore_50',
    ]
    mtf_extras = [f'htf_{k}' for k in htf_keys] + [
        'mtf_trend_aligned', 'mtf_trend_conflict',
        'mtf_confluence_bull', 'mtf_confluence_bear',
    ]
    return base_columns + mtf_extras
