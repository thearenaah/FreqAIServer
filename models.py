"""
Model Training & Prediction - TheArena FreqAI Server
=====================================================
Key upgrades over v1:
  1. XGBoost classifier (replaces RandomForest)
  2. Walk-forward validation (no data leakage)
  3. Risk-adjusted labels (SL-aware, not just future_high/low)
  4. Multi-timeframe feature merging at prediction time
  5. Regime-aware TP/SL calculation
  6. Separate trend + range models per symbol/timeframe

Author: TheArena Platform
"""

import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from features import FeatureEngineer, build_mtf_features, get_mtf_feature_columns, MTF_CHAIN
from regime_classifier import classify_regime_rules, calculate_tp_sl, should_emit_signal
from config import MODEL_PATH, FEATURE_WINDOW, TRAINING_WINDOW

logger = logging.getLogger(__name__)
Path(MODEL_PATH).mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
#  XGBoost import with graceful fallback to sklearn GBT
# ─────────────────────────────────────────────────────────────────────────────
try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
    logger.info("XGBoost available — using XGBClassifier")
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier
    HAS_XGBOOST = False
    logger.warning("XGBoost not installed — falling back to sklearn GradientBoostingClassifier. "
                   "Install with: pip install xgboost")

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                              precision_score, recall_score, f1_score)
from database import Model, TrainingData, TrainingJob


# ─────────────────────────────────────────────────────────────────────────────
#  Labelling
# ─────────────────────────────────────────────────────────────────────────────

LOOKAHEAD_MAP = {
    '1m': 20, '5m': 12, '15m': 8, '30m': 6,
    '1h': 5,  '4h': 5,  '1d': 5,  '1w': 3,
}

# Timeframe-aware SL/TP multipliers
# Longer TFs need looser ratios to prevent HOLD dominating (90%+) labels
SL_ATR_MULT_MAP = {
    '5m': 1.2, '15m': 1.3, '30m': 1.4,
    '1h': 1.5, '4h':  1.5, '1d':  1.2, '1w': 1.0,
}
TP_ATR_MULT_MAP = {
    '5m': 1.5, '15m': 1.6, '30m': 1.7,
    '1h': 1.8, '4h':  1.8, '1d':  1.5, '1w': 1.2,
}
SL_ATR_MULT = 1.5
TP_ATR_MULT = 2.0


def _label_trade_outcome(
    df: pd.DataFrame,
    i: int,
    lookahead: int,
    atr: float,
    timeframe: str = '1h',
) -> int:
    """
    Simulate a trade from candle i for 'lookahead' candles.
    Uses timeframe-aware SL/TP multiples to ensure balanced labels.
    Returns:
      +1  (BUY)  if TP_long  hit before SL_long
      -1  (SELL) if TP_short hit before SL_short
       0  (HOLD) if neither TP was hit cleanly OR price was ambiguous
    """
    sl_mult = SL_ATR_MULT_MAP.get(timeframe, SL_ATR_MULT)
    tp_mult = TP_ATR_MULT_MAP.get(timeframe, TP_ATR_MULT)

    entry = df['close'].iloc[i]
    sl_long   = entry - atr * sl_mult
    tp_long   = entry + atr * tp_mult
    sl_short  = entry + atr * sl_mult
    tp_short  = entry - atr * tp_mult

    long_hit  = False
    short_hit = False
    long_sl_hit  = False
    short_sl_hit = False

    end = min(i + lookahead + 1, len(df))
    for j in range(i + 1, end):
        h = df['high'].iloc[j]
        l = df['low'].iloc[j]

        # Long scenario
        if not long_hit and not long_sl_hit:
            if l <= sl_long:
                long_sl_hit = True     # SL hit first → losing long
            elif h >= tp_long:
                long_hit = True         # TP hit before SL → winning long

        # Short scenario
        if not short_hit and not short_sl_hit:
            if h >= sl_short:
                short_sl_hit = True
            elif l <= tp_short:
                short_hit = True

    if long_hit and not long_sl_hit:
        return 1    # clean BUY win
    if short_hit and not short_sl_hit:
        return -1   # clean SELL win
    return 0        # HOLD — messy or no clear outcome


# ─────────────────────────────────────────────────────────────────────────────
#  Walk-Forward splitter
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_splits(n: int, n_splits: int = 5, test_ratio: float = 0.15):
    """
    Generate (train_idx, test_idx) tuples for walk-forward validation.
    Each fold: train on everything before the test window, test on next slice.
    No shuffling — preserves temporal order.
    """
    test_size  = max(50, int(n * test_ratio))
    train_size = n - n_splits * test_size

    if train_size < 100:
        # Not enough data for WF — fall back to simple time split
        split = int(n * 0.80)
        yield np.arange(split), np.arange(split, n)
        return

    for k in range(n_splits):
        train_end  = train_size + k * test_size
        test_start = train_end
        test_end   = test_start + test_size
        if test_end > n:
            break
        yield np.arange(train_end), np.arange(test_start, test_end)


# ─────────────────────────────────────────────────────────────────────────────
#  ModelTrainer
# ─────────────────────────────────────────────────────────────────────────────

class ModelTrainer:

    def __init__(self):
        self.feature_engineer = FeatureEngineer()

    # ──────────────────────────────────────────────────────────────────────
    #  Data preparation
    # ──────────────────────────────────────────────────────────────────────

    def _load_df(self, db: Session, symbol: str, timeframe: str) -> pd.DataFrame:
        rows = (
            db.query(TrainingData)
            .filter(TrainingData.symbol == symbol,
                    TrainingData.timeframe == timeframe)
            .order_by(TrainingData.timestamp.asc())
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{
            'timestamp': r.timestamp,
            'open':  r.open,
            'high':  r.high,
            'low':   r.low,
            'close': r.close,
            'volume':r.volume,
        } for r in rows])

    def _load_higher_tf_features(
        self, db: Session, symbol: str, base_tf: str
    ) -> pd.DataFrame:
        """
        Load the higher timeframe features aligned to base-TF candle timestamps.
        Returns a DataFrame indexed by timestamp with feature columns prefixed htf_.
        Returns empty DataFrame if no HTF data.
        """
        htf = MTF_CHAIN.get(base_tf)
        if not htf or htf == base_tf:
            return pd.DataFrame()

        df_htf = self._load_df(db, symbol, htf)
        if df_htf.empty or len(df_htf) < FEATURE_WINDOW:
            return pd.DataFrame()

        htf_records = []
        for i in range(FEATURE_WINDOW, len(df_htf)):
            window = df_htf.iloc[i - FEATURE_WINDOW: i]
            ts = df_htf.iloc[i]['timestamp']
            feat = self.feature_engineer.calculate_advanced_features(window, timestamp=ts)
            feat['timestamp'] = ts
            htf_records.append(feat)

        if not htf_records:
            return pd.DataFrame()

        df_htf_feat = pd.DataFrame(htf_records).set_index('timestamp')
        return df_htf_feat

    def prepare_training_data(
        self,
        db: Session,
        symbol: str,
        timeframe: str,
        lookback_periods: int = TRAINING_WINDOW,
    ):
        """
        Prepare (X, y) training data with:
          - Risk-adjusted labels (SL-aware simulation)
          - Multi-timeframe feature enrichment
          - Walk-forward ready (chronological, no shuffle)
        """
        lookahead = LOOKAHEAD_MAP.get(timeframe, 5)
        df = self._load_df(db, symbol, timeframe)

        if df.empty or len(df) < FEATURE_WINDOW + lookahead + 20:
            raise ValueError(
                f"Insufficient data for {symbol} {timeframe}: "
                f"got {len(df)}, need {FEATURE_WINDOW + lookahead + 20}"
            )

        # Pre-compute ATR for the whole series (needed for labelling)
        atr_arr = FeatureEngineer.calculate_atr(
            df['high'].values, df['low'].values, df['close'].values, 14
        )

        # Load higher-TF feature table for MTF enrichment
        htf_df = self._load_higher_tf_features(db, symbol, timeframe)
        has_htf = not htf_df.empty

        features_list = []
        labels = []

        for i in range(FEATURE_WINDOW, len(df) - lookahead):
            window = df.iloc[i - FEATURE_WINDOW: i]
            ts = df.iloc[i]['timestamp']

            # Base features
            base_feat = self.feature_engineer.calculate_advanced_features(window, timestamp=ts)

            # HTF enrichment: find nearest previous HTF timestamp
            htf_feat = None
            if has_htf:
                valid = htf_df[htf_df.index <= ts]
                if not valid.empty:
                    htf_feat = valid.iloc[-1].to_dict()

            merged = build_mtf_features(base_feat, htf_feat)
            features_list.append(list(merged.values()))

            # Label: simulate trade with ATR-based SL/TP
            atr_val = float(atr_arr[i]) if not np.isnan(atr_arr[i]) else (df['close'].iloc[i] * 0.01)
            label   = _label_trade_outcome(df, i, lookahead, atr_val, timeframe)
            labels.append(label)

        X = np.array(features_list, dtype=np.float32)
        y = np.array(labels,        dtype=np.int32)

        # Replace any NaN/Inf that slipped through
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        buy_n  = int(np.sum(y ==  1))
        sell_n = int(np.sum(y == -1))
        hold_n = int(np.sum(y ==  0))
        logger.info(
            f"[LABELS] {symbol} {timeframe} — "
            f"BUY:{buy_n} SELL:{sell_n} HOLD:{hold_n} "
            f"Total:{len(y)} Features:{X.shape[1]}"
        )
        return X, y

    # ──────────────────────────────────────────────────────────────────────
    #  Model building
    # ──────────────────────────────────────────────────────────────────────

    def _build_model(self):
        """Return a fresh XGBoost (or fallback sklearn GBT) classifier."""
        if HAS_XGBOOST:
            return XGBClassifier(
                n_estimators=400,
                learning_rate=0.03,
                max_depth=6,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=0.1,
                reg_alpha=0.05,
                reg_lambda=1.0,
                eval_metric='mlogloss',
                random_state=42,
                n_jobs=-1,
                tree_method='hist',   # fast on CPU
            )
        else:
            from sklearn.ensemble import GradientBoostingClassifier
            return GradientBoostingClassifier(
                n_estimators=300,
                learning_rate=0.04,
                max_depth=5,
                subsample=0.8,
                min_samples_split=5,
                random_state=42,
            )

    # ──────────────────────────────────────────────────────────────────────
    #  Training
    # ──────────────────────────────────────────────────────────────────────

    def train_model(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Train with walk-forward validation.
        Labels: -1=SELL → class 0 | 0=HOLD → class 1 | 1=BUY → class 2
        """
        # Remap labels
        y_mapped = np.where(y == -1, 0, np.where(y == 1, 2, 1)).astype(np.int32)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # ── Walk-forward evaluation ────────────────────────────────────
        wf_scores = []
        n_splits   = min(5, len(X) // 200)   # at least 200 samples per fold

        if n_splits >= 2:
            for train_idx, test_idx in walk_forward_splits(len(X), n_splits):
                m = self._build_model()
                Xtr, ytr = X_scaled[train_idx], y_mapped[train_idx]
                Xte, yte = X_scaled[test_idx],  y_mapped[test_idx]

                # Class weights to handle imbalance
                classes, counts = np.unique(ytr, return_counts=True)
                weights = {int(c): float(len(ytr)) / (len(classes) * cnt)
                           for c, cnt in zip(classes, counts)}
                sample_weights = np.array([weights[int(yi)] for yi in ytr])

                if HAS_XGBOOST:
                    m.fit(Xtr, ytr, sample_weight=sample_weights,
                          eval_set=[(Xte, yte)], verbose=False)
                else:
                    m.fit(Xtr, ytr, sample_weight=sample_weights)

                y_pred = m.predict(Xte)
                ba = balanced_accuracy_score(yte, y_pred)
                wf_scores.append(ba)
                logger.info(f"  WF fold balanced_acc={ba:.4f}")

            avg_wf_ba = float(np.mean(wf_scores))
            logger.info(f"Walk-forward avg balanced_acc = {avg_wf_ba:.4f}")
        else:
            avg_wf_ba = 0.0

        # ── Final model on ALL data ────────────────────────────────────
        classes, counts = np.unique(y_mapped, return_counts=True)
        weights = {int(c): float(len(y_mapped)) / (len(classes) * cnt)
                   for c, cnt in zip(classes, counts)}
        sample_weights = np.array([weights[int(yi)] for yi in y_mapped])

        final_model = self._build_model()
        if HAS_XGBOOST:
            # Hold out last 15% for early stopping
            split = int(len(X_scaled) * 0.85)
            Xtr_, ytr_ = X_scaled[:split], y_mapped[:split]
            Xte_, yte_ = X_scaled[split:], y_mapped[split:]
            sw_ = sample_weights[:split]
            final_model.fit(
                Xtr_, ytr_,
                sample_weight=sw_,
                eval_set=[(Xte_, yte_)],
                verbose=False,
            )
            y_pred_final = final_model.predict(Xte_)
            accuracy     = accuracy_score(yte_, y_pred_final)
            balanced_acc = balanced_accuracy_score(yte_, y_pred_final)
            precision    = precision_score(yte_, y_pred_final, average='weighted', zero_division=0)
            recall       = recall_score(yte_, y_pred_final, average='weighted', zero_division=0)
            f1           = f1_score(yte_, y_pred_final, average='weighted', zero_division=0)
        else:
            split = int(len(X_scaled) * 0.85)
            Xtr_, ytr_ = X_scaled[:split], y_mapped[:split]
            Xte_, yte_ = X_scaled[split:], y_mapped[split:]
            final_model.fit(Xtr_, ytr_, sample_weight=sample_weights[:split])
            y_pred_final = final_model.predict(Xte_)
            accuracy     = accuracy_score(yte_, y_pred_final)
            balanced_acc = balanced_accuracy_score(yte_, y_pred_final)
            precision    = precision_score(yte_, y_pred_final, average='weighted', zero_division=0)
            recall       = recall_score(yte_, y_pred_final, average='weighted', zero_division=0)
            f1           = f1_score(yte_, y_pred_final, average='weighted', zero_division=0)

        logger.info(
            f"Final model — acc={accuracy:.4f} bal_acc={balanced_acc:.4f} "
            f"prec={precision:.4f} recall={recall:.4f} f1={f1:.4f} "
            f"wf_avg={avg_wf_ba:.4f}"
        )

        return {
            'model':               final_model,
            'scaler':              scaler,
            'accuracy':            accuracy,
            'balanced_accuracy':   balanced_acc,
            'precision':           precision,
            'recall':              recall,
            'f1_score':            f1,
            'wf_balanced_accuracy':avg_wf_ba,
            'model_type':          'XGBoost' if HAS_XGBOOST else 'GradientBoosting',
        }

    # ──────────────────────────────────────────────────────────────────────
    #  Async training (called from FastAPI background task)
    # ──────────────────────────────────────────────────────────────────────

    def train_model_async(self, model_id: int, symbol: str,
                          timeframe: str, db: Session = None):
        if db is None:
            from database import SessionLocal
            db = SessionLocal()

        job = None
        try:
            job = (db.query(TrainingJob)
                   .filter(TrainingJob.model_id == model_id)
                   .order_by(TrainingJob.id.desc()).first())
            if job:
                job.status = 'running'
                job.started_at = datetime.utcnow()
                db.commit()

            X, y = self.prepare_training_data(db, symbol, timeframe)
            result = self.train_model(X, y)

            safe_sym  = symbol.replace('/', '_')
            model_path  = f"{MODEL_PATH}/{safe_sym}_{timeframe}_model.pkl"
            scaler_path = f"{MODEL_PATH}/{safe_sym}_{timeframe}_scaler.pkl"
            Path(model_path).parent.mkdir(parents=True, exist_ok=True)

            joblib.dump(result['model'],  model_path)
            joblib.dump(result['scaler'], scaler_path)

            m = db.query(Model).filter(Model.id == model_id).first()
            if m:
                m.model_type   = result['model_type']
                m.accuracy     = result['accuracy']
                m.precision    = result['precision']
                m.recall       = result['recall']
                m.f1_score     = result['f1_score']
                m.is_active    = True
                m.is_deployed  = True
                m.model_path   = model_path
                m.trained_at   = datetime.utcnow()
                db.commit()

            if job:
                job.status       = 'completed'
                job.completed_at = datetime.utcnow()
                job.progress     = 100
                db.commit()

            logger.info(f"Training completed: {symbol} {timeframe} "
                        f"(bal_acc={result['balanced_accuracy']:.3f})")

        except Exception as e:
            logger.error(f"Training failed {symbol} {timeframe}: {e}", exc_info=True)
            if job:
                job.status        = 'failed'
                job.error_message = str(e)
                job.completed_at  = datetime.utcnow()
                db.commit()
        finally:
            db.close()

    # ──────────────────────────────────────────────────────────────────────
    #  Prediction
    # ──────────────────────────────────────────────────────────────────────

    def predict(self, model: Model, db: Session) -> dict:
        """
        Generate a prediction for a given model.
        Includes:
          - MTF feature enrichment at inference time
          - Regime classification
          - Regime-aware TP/SL
          - Signal gating (regime + confidence filter)
        """
        model_path  = model.model_path
        scaler_path = model_path.replace('_model.pkl', '_scaler.pkl')

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        if not Path(scaler_path).exists():
            raise FileNotFoundError(f"Scaler not found: {scaler_path}")

        ml_model = joblib.load(model_path)
        scaler   = joblib.load(scaler_path)

        # ── Load base-TF candles ──────────────────────────────────────
        latest_rows = (
            db.query(TrainingData)
            .filter(TrainingData.symbol == model.symbol,
                    TrainingData.timeframe == model.timeframe)
            .order_by(TrainingData.timestamp.desc())
            .limit(FEATURE_WINDOW)
            .all()
        )
        if not latest_rows or len(latest_rows) < FEATURE_WINDOW:
            raise ValueError(
                f"Insufficient data for {model.symbol} {model.timeframe}: "
                f"need {FEATURE_WINDOW}, have {len(latest_rows) if latest_rows else 0}"
            )

        latest_rows = list(reversed(latest_rows))
        df_base = pd.DataFrame([{
            'timestamp': r.timestamp,
            'open':  r.open, 'high':  r.high,
            'low':   r.low,  'close': r.close,
            'volume':r.volume,
        } for r in latest_rows])

        ts_last = df_base['timestamp'].iloc[-1]

        # ── Base features ────────────────────────────────────────────
        base_feat = self.feature_engineer.calculate_advanced_features(df_base, timestamp=ts_last)

        # ── HTF features ─────────────────────────────────────────────
        htf = MTF_CHAIN.get(model.timeframe)
        htf_feat = None
        if htf and htf != model.timeframe:
            htf_rows = (
                db.query(TrainingData)
                .filter(TrainingData.symbol == model.symbol,
                        TrainingData.timeframe == htf)
                .order_by(TrainingData.timestamp.desc())
                .limit(FEATURE_WINDOW)
                .all()
            )
            if htf_rows and len(htf_rows) >= FEATURE_WINDOW:
                htf_rows = list(reversed(htf_rows))
                df_htf = pd.DataFrame([{
                    'timestamp': r.timestamp,
                    'open':  r.open, 'high':  r.high,
                    'low':   r.low,  'close': r.close,
                    'volume':r.volume,
                } for r in htf_rows])
                htf_feat = self.feature_engineer.calculate_advanced_features(
                    df_htf, timestamp=df_htf['timestamp'].iloc[-1]
                )

        merged_feat = build_mtf_features(base_feat, htf_feat)
        feature_values = np.array(list(merged_feat.values()), dtype=np.float32).reshape(1, -1)
        feature_values = np.nan_to_num(feature_values, nan=0.0, posinf=0.0, neginf=0.0)

        # ── Feature count guard ───────────────────────────────────────
        expected = scaler.n_features_in_
        actual   = feature_values.shape[1]
        if actual != expected:
            if actual < expected:
                feature_values = np.pad(feature_values, ((0, 0), (0, expected - actual)))
            else:
                feature_values = feature_values[:, :expected]
            logger.warning(f"Feature count mismatch: expected {expected}, got {actual} — adjusted")

        # ── Scale & predict ───────────────────────────────────────────
        feat_scaled  = scaler.transform(feature_values)
        probabilities = ml_model.predict_proba(feat_scaled)[0]

        class_labels = ml_model.classes_
        prob_map = {int(c): float(p) for c, p in zip(class_labels, probabilities)}
        prob_sell = prob_map.get(0, 0.0)
        prob_hold = prob_map.get(1, 0.0)
        prob_buy  = prob_map.get(2, 0.0)

        predicted_class = int(ml_model.predict(feat_scaled)[0])
        if predicted_class == 2:
            signal, confidence = 'BUY',  prob_buy
        elif predicted_class == 0:
            signal, confidence = 'SELL', prob_sell
        else:
            signal, confidence = 'HOLD', prob_hold

        # ── Regime classification ─────────────────────────────────────
        regime = classify_regime_rules(base_feat)

        # ── Signal gating ─────────────────────────────────────────────
        if signal != 'HOLD':
            allowed, gate_reason = should_emit_signal(
                signal, confidence, merged_feat, model.timeframe
            )
            if not allowed:
                logger.info(f"Signal gated [{model.symbol} {model.timeframe}]: {gate_reason}")
                signal     = 'HOLD'
                confidence = prob_hold

        # ── TP/SL ─────────────────────────────────────────────────────
        latest_close = float(latest_rows[-1].close)
        atr_ratio    = base_feat.get('volatility_atr', 0.0)
        atr_price    = atr_ratio * latest_close   # convert ratio → price units

        tp_sl = {}
        if signal != 'HOLD' and atr_price > 0:
            tp_sl = calculate_tp_sl(signal, latest_close, atr_price, regime)

        # Clean features for JSON storage
        clean_feat = {}
        for k, v in merged_feat.items():
            try:
                fv = float(v)
                clean_feat[k] = 0.0 if (np.isnan(fv) or np.isinf(fv)) else fv
            except Exception:
                clean_feat[k] = 0.0

        return {
            'signal':            signal,
            'confidence':        float(confidence),
            'probability_buy':   prob_buy,
            'probability_sell':  prob_sell,
            'probability_hold':  prob_hold,
            'entry_price':       latest_close,
            'stop_loss':         tp_sl.get('stop_loss'),
            'take_profit_1':     tp_sl.get('take_profit_1'),
            'take_profit_2':     tp_sl.get('take_profit_2'),
            'take_profit_3':     tp_sl.get('take_profit_3'),
            'atr':               atr_price if atr_price > 0 else None,
            'regime':            regime.regime_name,
            'regime_adx':        regime.adx,
            'regime_confidence': regime.confidence,
            'features':          clean_feat,
            'pivot_points':      {},
        }
