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
from strategy_rules import StrategyEngine, StrategyRules, Signal
from config import MODEL_PATH, FEATURE_WINDOW, TRAINING_WINDOW

logger = logging.getLogger(__name__)

# Create models directory
Path(MODEL_PATH).mkdir(parents=True, exist_ok=True)


class ModelTrainer:
    """Train and manage ML models for trading signals"""
    
    def __init__(self):
        self.feature_engineer = FeatureEngineer()
        self.scaler = StandardScaler()
        self.strategy_rules = StrategyRules()
        self.strategy_engine = StrategyEngine(self.strategy_rules)
    
    def prepare_training_data(
        self,
        db: Session,
        symbol: str,
        timeframe: str,
        lookback_periods: int = TRAINING_WINDOW
    ) -> tuple:
        """
        Prepare training data from database
        Returns X (features) and y (target labels)
        """
        # Get historical data
        data = db.query(TrainingData).filter(
            TrainingData.symbol == symbol,
            TrainingData.timeframe == timeframe
        ).order_by(TrainingData.timestamp.desc()).limit(lookback_periods * 2).all()
        
        if not data:
            raise ValueError(f"No training data found for {symbol} {timeframe}")
        
        # Reverse to chronological order
        data = list(reversed(data))
        
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
        
        for i in range(FEATURE_WINDOW, len(df) - 1):
            window = df.iloc[i-FEATURE_WINDOW:i]
            
            # Calculate features for this window
            features = self.feature_engineer.calculate_price_features(window)
            features_list.append(list(features.values()))
            
            # Professional label: Use strategy engine to determine if this was a good buy/sell
            # Label: 1 if strategy would generate BUY and price goes up
            #        0 if strategy would generate SELL or price goes down
            try:
                current_row = df.iloc[i]
                next_row = df.iloc[i + 1]
                
                # Get professional features including pivot points and patterns
                prof_features = self.feature_engineer.calculate_professional_features(
                    window, include_patterns=True
                )
                
                if prof_features and 'signal_analysis' in prof_features:
                    signal_analysis = prof_features['signal_analysis']
                    
                    # Did the price go up or down?
                    price_went_up = next_row['close'] > current_row['close']
                    
                    # Was it a profitable BUY signal?
                    was_buy_profitable = (
                        signal_analysis['long_signal'] == 'LONG' and price_went_up
                    )
                    
                    # Was it a profitable SELL signal?
                    was_sell_profitable = (
                        signal_analysis['short_signal'] == 'SHORT' and not price_went_up
                    )
                    
                    # Label: 1 for profitable trades following strategy, 0 otherwise
                    label = 1 if (was_buy_profitable or was_sell_profitable) else 0
                else:
                    # Fallback: simple price direction
                    label = 1 if next_row['close'] > current_row['close'] else 0
            except Exception as e:
                # Fallback on any error
                logger.warning(f"Error generating label at index {i}: {e}")
                future_close = df.iloc[i + 1]['close']
                current_close = df.iloc[i]['close']
                label = 1 if future_close > current_close else 0
            
            labels.append(label)
        
        X = np.array(features_list)
        y = np.array(labels)
        
        logger.info(f"Prepared {len(X)} training samples with {X.shape[1]} features")
        
        return X, y
    
    def train_model(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str = "RandomForest"
    ) -> dict:
        """
        Train ML model
        """
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=True
        )
        
        # Normalize features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        if model_type == "RandomForest":
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=20,
                min_samples_split=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1
            )
        else:  # GradientBoosting
            model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
        
        model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test_scaled)
        
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        
        logger.info(
            f"Model trained - Accuracy: {accuracy:.4f}, "
            f"Precision: {precision:.4f}, Recall: {recall:.4f}, F1: {f1:.4f}"
        )
        
        return {
            "model": model,
            "scaler": self.scaler,
            "accuracy": accuracy,
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
            
            # Save model files
            model_path = f"{MODEL_PATH}/{symbol}_{timeframe}_model.pkl"
            scaler_path = f"{MODEL_PATH}/{symbol}_{timeframe}_scaler.pkl"
            
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
        Make prediction using trained model + strategy rules engine
        Returns professional trading signal with confidence from strategy
        """
        try:
            # Load model and scaler
            ml_model = joblib.load(model.model_path)
            scaler_path = model.model_path.replace("_model.pkl", "_scaler.pkl")
            scaler = joblib.load(scaler_path)
            
            # Get latest data for features
            latest_data = db.query(TrainingData).filter(
                TrainingData.symbol == model.symbol,
                TrainingData.timeframe == model.timeframe
            ).order_by(TrainingData.timestamp.desc()).limit(
                FEATURE_WINDOW
            ).all()
            
            if not latest_data:
                return {
                    "signal": "HOLD",
                    "confidence": 0.0,
                    "ml_probability": 0.5,
                    "strategy_signal": "HOLD",
                    "strategy_confidence": 0.0,
                    "reasons": ["Insufficient data"],
                    "features": {}
                }
            
            # Reverse chronological order
            latest_data = list(reversed(latest_data))
            
            # Create DataFrame
            df = pd.DataFrame([{
                'timestamp': d.timestamp,
                'open': d.open,
                'high': d.high,
                'low': d.low,
                'close': d.close,
                'volume': d.volume,
            } for d in latest_data])
            
            # Get professional features with strategy analysis
            prof_features = self.feature_engineer.calculate_professional_features(
                df, include_patterns=True
            )
            
            # Extract strategy signals
            strategy_signal = "HOLD"
            strategy_confidence = 0.0
            strategy_reasons = []
            
            if prof_features and 'signal_analysis' in prof_features:
                signal_analysis = prof_features['signal_analysis']
                
                # Check LONG signal strength
                long_signal = signal_analysis['long_signal']
                long_confidence = signal_analysis['long_confidence']
                long_reasons = signal_analysis['long_reasons']
                
                # Check SHORT signal strength
                short_signal = signal_analysis['short_signal']
                short_confidence = signal_analysis['short_confidence']
                short_reasons = signal_analysis['short_reasons']
                
                # Determine primary signal
                if long_confidence > short_confidence and long_confidence > 0.5:
                    strategy_signal = "LONG"
                    strategy_confidence = long_confidence
                    strategy_reasons = long_reasons
                elif short_confidence > long_confidence and short_confidence > 0.5:
                    strategy_signal = "SHORT"
                    strategy_confidence = short_confidence
                    strategy_reasons = short_reasons
                else:
                    strategy_signal = "HOLD"
                    strategy_confidence = 0.0
                    strategy_reasons = ["No clear signal above confidence threshold"]
            
            # Also get ML model prediction for comparison
            features = self.feature_engineer.calculate_price_features(df)
            feature_values = np.array(list(features.values())).reshape(1, -1)
            
            # Scale features
            feature_scaled = scaler.transform(feature_values)
            
            # Make ML prediction
            probabilities = ml_model.predict_proba(feature_scaled)[0]
            
            # Binary classification: 0 = sell/short, 1 = buy/long
            prob_short = probabilities[0]
            prob_long = probabilities[1]
            
            # Determine ML signal
            ml_signal = "LONG" if prob_long > prob_short else "SHORT"
            ml_probability = max(prob_long, prob_short)
            
            # Final signal combines both strategies with higher weight on strategy rules
            if strategy_confidence > 0.5:
                final_signal = strategy_signal
                final_confidence = strategy_confidence
                final_reasons = strategy_reasons + [
                    f"ML model confidence: {ml_probability:.2f} ({ml_signal})"
                ]
            else:
                # Fall back to ML signal if strategy is uncertain
                final_signal = ml_signal
                final_confidence = ml_probability
                final_reasons = [
                    f"Strategy confidence below threshold, using ML: {ml_probability:.2f}"
                ]
            
            return {
                "signal": final_signal,
                "confidence": float(final_confidence),
                "ml_probability": float(ml_probability),
                "ml_signal": ml_signal,
                "strategy_signal": strategy_signal,
                "strategy_confidence": float(strategy_confidence),
                "reasons": final_reasons,
                "features": features,
                "pivot_points": prof_features.get('pivot_points', {}),
                "candle_patterns": prof_features.get('candle_patterns', {}),
            }
        
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "ml_probability": 0.5,
                "strategy_signal": "HOLD",
                "strategy_confidence": 0.0,
                "reasons": [str(e)],
                "features": {}
            }
