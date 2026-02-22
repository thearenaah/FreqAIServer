"""
Model training and prediction service
"""
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
import logging

from database import Model, TrainingData, Prediction, TrainingJob
from features import FeatureEngineer
from config import MODEL_PATH, FEATURE_WINDOW, TRAINING_WINDOW

logger = logging.getLogger(__name__)

# Create models directory
Path(MODEL_PATH).mkdir(parents=True, exist_ok=True)


class ModelTrainer:
    """Train and manage ML models for trading signals"""
    
    def __init__(self):
        self.feature_engineer = FeatureEngineer()
        self.scaler = StandardScaler()
    
    def prepare_training_data(
        self,
        db: Session,
        symbol: str,
        timeframe: str,
        lookback_periods: int = TRAINING_WINDOW
    ) -> tuple:
        """
        Prepare training data with improved multi-period labels
        Uses aggressive labeling for better class balance and model learning
        """
        # Determine lookahead based on timeframe
        lookahead_map = {
            '1m': 20,   # 20 candles = 20 minutes
            '5m': 12,   # 12 candles = 60 minutes (1 hour)
            '15m': 8,   # 8 candles = 120 minutes (2 hours)
            '30m': 6,   # 6 candles = 180 minutes (3 hours)
            '1h': 5,    # 5 candles = 5 hours
            '4h': 5,    # 5 candles = 20 hours
            '1d': 3,    # 3 candles = 3 days
        }
        lookahead = lookahead_map.get(timeframe, 5)
        
        # Improved minimum percentage move for better class balance
        # Using 0.2% instead of 0.5% allows capturing more trading opportunities
        min_pct_move = 0.002  # 0.2% (aggressive/improved strategy)
        
        # Get historical data
        data = db.query(TrainingData).filter(
            TrainingData.symbol == symbol,
            TrainingData.timeframe == timeframe
        ).order_by(TrainingData.timestamp.asc()).all()
        
        if not data or len(data) < FEATURE_WINDOW + lookahead:
            raise ValueError(f"Insufficient data for {symbol} {timeframe}: need {FEATURE_WINDOW + lookahead}, got {len(data)}")
        
        # Convert to DataFrame
        df = pd.DataFrame([{
            'timestamp': d.timestamp,
            'open': d.open,
            'high': d.high,
            'low': d.low,
            'close': d.close,
            'volume': d.volume,
        } for d in data])
        
        # Calculate features
        features_list = []
        labels = []
        
        for i in range(FEATURE_WINDOW, len(df) - lookahead):
            window = df.iloc[i-FEATURE_WINDOW:i]
            
            # Calculate advanced features (35+)
            features = self.feature_engineer.calculate_advanced_features(window)
            features_list.append(list(features.values()))
            
            # Smart label: Multi-period move prediction with AGGRESSIVE labeling
            current_close = df.iloc[i]['close']
            future_close = df.iloc[i + lookahead]['close']
            future_high = df.iloc[i:i+lookahead+1]['high'].max()
            future_low = df.iloc[i:i+lookahead+1]['low'].min()
            
            # Calculate moves
            upside_pct = (future_high - current_close) / (current_close + 1e-10)
            downside_pct = (current_close - future_low) / (current_close + 1e-10)
            
            # Aggressive label logic for better BUY/SELL distribution
            # Using 0.25% threshold with minimal ratio requirement (1.05x)
            # This creates ~20-25% actionable signals (BUY+SELL) and ~75% HOLD
            if upside_pct >= 0.0025 and upside_pct > downside_pct * 1.05:
                label = 1  # BUY signal - upside potential detected
            elif downside_pct >= 0.0025 and downside_pct > upside_pct * 1.05:
                label = -1  # SELL signal - downside risk detected
            else:
                label = 0  # HOLD - balanced or insufficient move
            
            labels.append(label)
        
        X = np.array(features_list)
        y = np.array(labels)
        
        logger.info(
            f"Prepared {len(X)} samples for {symbol} {timeframe} | "
            f"BUY:{sum(y==1)} SELL:{sum(y==-1)} HOLD:{sum(y==0)} | "
            f"Features: {X.shape[1]}"
        )
        
        return X, y
    
    def train_model(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str = "RandomForest"
    ) -> dict:
        """
        Train ML model (3-class: BUY, HOLD, SELL)
        """
        # Remap labels: -1 -> SELL (class 0), 0 -> HOLD (class 1), 1 -> BUY (class 2)
        y_mapped = np.where(y == -1, 0, np.where(y == 1, 2, 1))
        
        # Split data with stratification for balanced classes
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_mapped, test_size=0.2, random_state=42, shuffle=True, stratify=y_mapped
        )
        
        # Normalize features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model with better hyperparameters
        if model_type == "RandomForest":
            model = RandomForestClassifier(
                n_estimators=200,        # Increased from 100
                max_depth=25,            # Increased from 20
                min_samples_split=5,     # Decreased from 10
                min_samples_leaf=2,      # Decreased from 5
                max_features='sqrt',     # Better feature selection
                class_weight='balanced',  # Handle imbalanced classes
                random_state=42,
                n_jobs=-1
            )
        else:  # GradientBoosting
            model = GradientBoostingClassifier(
                n_estimators=200,        # Increased from 100
                learning_rate=0.05,      # Decreased from 0.1 (slower, more stable)
                max_depth=6,             # Increased from 5
                subsample=0.8,           # Prevent overfitting
                min_samples_split=5,
                random_state=42
            )
        
        model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test_scaled)
        
        from sklearn.metrics import f1_score as f1_multi, balanced_accuracy_score
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        f1 = f1_multi(y_test, y_pred, average='weighted', zero_division=0)
        balanced_acc = balanced_accuracy_score(y_test, y_pred)
        
        logger.info(
            f"Model trained - Accuracy: {accuracy:.4f}, "
            f"Balanced Acc: {balanced_acc:.4f}, Precision: {precision:.4f}, "
            f"Recall: {recall:.4f}, F1: {f1:.4f}"
        )
        
        return {
            "model": model,
            "scaler": self.scaler,
            "accuracy": accuracy,
            "balanced_accuracy": balanced_acc,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "feature_names": FeatureEngineer.get_feature_columns()
        }
    
    def train_model_async(
        self,
        model_id: int,
        symbol: str,
        timeframe: str,
        db: Session = None
    ):
        """
        Async model training (for background tasks)
        """
        if db is None:
            from database import SessionLocal
            db = SessionLocal()
        
        try:
            # Get training job
            job = db.query(TrainingJob).filter(
                TrainingJob.model_id == model_id
            ).order_by(TrainingJob.id.desc()).first()
            
            if job:
                job.status = "running"
                job.started_at = datetime.utcnow()
                db.commit()
            
            # Prepare data
            X, y = self.prepare_training_data(db, symbol, timeframe)
            
            # Train model
            result = self.train_model(X, y)
            
            # Save model files (sanitize symbol for file path)
            safe_symbol = symbol.replace('/', '_')
            model_path = f"{MODEL_PATH}/{safe_symbol}_{timeframe}_model.pkl"
            scaler_path = f"{MODEL_PATH}/{safe_symbol}_{timeframe}_scaler.pkl"
            
            # Create subdirectory if needed
            Path(model_path).parent.mkdir(parents=True, exist_ok=True)
            
            joblib.dump(result['model'], model_path)
            joblib.dump(result['scaler'], scaler_path)
            
            # Update model record
            model = db.query(Model).filter(Model.id == model_id).first()
            if model:
                model.model_type = "RandomForest"
                model.accuracy = result['accuracy']
                model.precision = result['precision']
                model.recall = result['recall']
                model.f1_score = result['f1_score']
                model.is_active = True
                model.is_deployed = True
                model.model_path = model_path
                model.trained_at = datetime.utcnow()
                db.commit()
            
            # Update job
            if job:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                job.progress = 100
                db.commit()
            
            logger.info(f"Model training completed for {symbol} {timeframe}")
            
        except Exception as e:
            logger.error(f"Model training failed: {e}")
            
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()
        
        finally:
            db.close()
    
    def predict(self, model: Model, db: Session) -> dict:
        """
        Pure ML prediction. No rule-based fallback.
        Returns the ML model's signal and class probabilities.
        Raises exception if model file is missing (caller handles 404).
        """
        import joblib
        import numpy as np
        import pandas as pd
        from pathlib import Path

        # ---- 1. Load ML model and scaler (raise if missing) ----
        model_path = model.model_path
        scaler_path = model_path.replace('_model.pkl', '_scaler.pkl')

        if not Path(model_path).exists():
            raise FileNotFoundError(f'Model file not found: {model_path}')
        if not Path(scaler_path).exists():
            raise FileNotFoundError(f'Scaler file not found: {scaler_path}')

        ml_model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)

        # ---- 2. Load latest candles ----
        from database import TrainingData
        from config import FEATURE_WINDOW
        latest_data = db.query(TrainingData).filter(
            TrainingData.symbol == model.symbol,
            TrainingData.timeframe == model.timeframe
        ).order_by(TrainingData.timestamp.desc()).limit(FEATURE_WINDOW).all()

        if not latest_data or len(latest_data) < FEATURE_WINDOW:
            raise ValueError(
                f'Insufficient data for {model.symbol} {model.timeframe}: '
                f'need {FEATURE_WINDOW}, have {len(latest_data) if latest_data else 0}'
            )

        latest_data = list(reversed(latest_data))  # chronological order

        df = pd.DataFrame([{
            'timestamp': d.timestamp,
            'open': d.open,
            'high': d.high,
            'low': d.low,
            'close': d.close,
            'volume': d.volume,
        } for d in latest_data])

        # ---- 3. Calculate features ----
        features = self.feature_engineer.calculate_price_features(df)
        feature_values = np.array(list(features.values())).reshape(1, -1)

        # ---- 4. Scale features ----
        feature_scaled = scaler.transform(feature_values)

        # ---- 5. ML prediction ----
        # Model has 3 classes: 0=SELL, 1=HOLD, 2=BUY
        probabilities = ml_model.predict_proba(feature_scaled)[0]

        # Map class indices to labels
        class_labels = ml_model.classes_  # typically [0, 1, 2]
        prob_map = {cls: float(prob) for cls, prob in zip(class_labels, probabilities)}

        prob_sell = prob_map.get(0, 0.0)
        prob_hold = prob_map.get(1, 0.0)
        prob_buy  = prob_map.get(2, 0.0)

        # Highest probability wins
        predicted_class = int(ml_model.predict(feature_scaled)[0])

        if predicted_class == 2:
            signal = 'BUY'
            confidence = prob_buy
        elif predicted_class == 0:
            signal = 'SELL'
            confidence = prob_sell
        else:
            signal = 'HOLD'
            confidence = prob_hold

        # ---- 6. Get latest close for TP/SL calculation ----
        latest_close = float(latest_data[-1].close)
        atr_val = features.get('atr_14', None)

        # Clean features for JSON storage
        cleaned_features = {}
        for k, v in features.items():
            if v is None or (isinstance(v, float) and (v != v or abs(v) == float('inf'))):
                cleaned_features[k] = 0
            else:
                cleaned_features[k] = v

        return {
            'signal': signal,
            'confidence': float(confidence),
            'probability_buy': prob_buy,
            'probability_sell': prob_sell,
            'probability_hold': prob_hold,
            'entry_price': latest_close,
            'atr': float(atr_val) if atr_val else None,
            'features': cleaned_features,
            'pivot_points': {},  # removed rule-based pivots
        }
