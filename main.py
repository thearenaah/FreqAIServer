"""
FastAPI application for FreqAI trading signal server
"""
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
import logging
import numpy as np

from database import init_db, get_db, Model, Prediction, TrainingData, TrainingJob
from config import HOST, PORT, DEBUG, ALLOWED_ORIGINS
from market_data import MarketDataFetcher
from features import FeatureEngineer
from models import ModelTrainer
from risk_management import RiskManagement, RiskManagementConfig
from regime_classifier import classify_regime_rules, calculate_tp_sl, RegimeResult, REGIME_RANGING

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="FreqAI Trading Signals Server",
    description="ML-powered trading signal generation service",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
fetcher = MarketDataFetcher()
engineer = FeatureEngineer()
trainer = ModelTrainer()


# ============================================================================
# Pydantic Models
# ============================================================================

class TrainingDataRequest(BaseModel):
    symbol: str
    timeframe: str
    limit: int = 100


class PredictionRequest(BaseModel):
    symbol: str
    timeframe: str
    model_id: Optional[int] = None


class PredictionResponse(BaseModel):
    model_config = {"exclude_none": False}

    symbol: str
    timeframe: str
    signal: str
    confidence: float
    probability_buy: float
    probability_sell: float
    probability_hold: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    atr: Optional[float] = None
    regime: Optional[str] = None
    regime_adx: Optional[float] = None
    regime_confidence: Optional[float] = None
    pivot_support_1: Optional[float] = None
    pivot_resistance_1: Optional[float] = None
    timestamp: datetime


class ModelInfo(BaseModel):
    id: int
    name: str
    symbol: str
    timeframe: str
    version: int
    accuracy: Optional[float]
    is_active: bool
    is_deployed: bool
    trained_at: datetime


class HealthResponse(BaseModel):
    status: str
    database: str
    models_count: int
    timestamp: datetime


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health(db: Session = Depends(get_db)):
    try:
        models_count = db.query(Model).count()
        return {
            "status": "healthy",
            "database": "connected",
            "models_count": models_count,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Service unhealthy")


@app.post("/api/v1/train")
async def train_model(
    request: TrainingDataRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        safe_symbol = request.symbol.replace('/', '_')
        model_path = f"./models/{safe_symbol}_{request.timeframe}_model.pkl"

        existing_model = db.query(Model).filter(
            Model.symbol == request.symbol,
            Model.timeframe == request.timeframe
        ).first()

        if existing_model:
            model = existing_model
            model.version += 1
            model.trained_at = datetime.utcnow()
            model.name = f"{request.symbol}_{request.timeframe}_v{model.version}"
            model.model_path = model_path
            model.is_active = False
            model.is_deployed = False
            db.commit()
            db.refresh(model)
            logger.info(f"Updating model {model.id} to version {model.version}")
        else:
            model = Model(
                name=f"{request.symbol}_{request.timeframe}_v1",
                symbol=request.symbol,
                timeframe=request.timeframe,
                version=1,
                trained_at=datetime.utcnow(),
                model_path=model_path,
                is_active=False,
                is_deployed=False
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            logger.info(f"Created new model {model.id}")

        job = TrainingJob(model_id=model.id, status="pending")
        db.add(job)
        db.commit()

        background_tasks.add_task(
            trainer.train_model_async,
            model_id=model.id,
            symbol=request.symbol,
            timeframe=request.timeframe
        )

        return {
            "message": "Training started",
            "model_id": model.id,
            "job_id": job.id,
            "status": "pending",
            "model_version": model.version
        }
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/predict", response_model=PredictionResponse)
async def predict_signal(
    request: PredictionRequest,
    db: Session = Depends(get_db)
):
    try:
        models = db.query(Model).filter(
            Model.symbol == request.symbol,
            Model.timeframe == request.timeframe,
            Model.is_deployed == True
        ).order_by(Model.accuracy.desc()).all()

        if not models:
            raise HTTPException(
                status_code=404,
                detail=f"No active model for {request.symbol} {request.timeframe}"
            )

        model = models[0]

        try:
            prediction = trainer.predict(model, db)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=404, detail=str(e))

        # Clean features
        features = prediction.get('features', {})
        cleaned_features = {}
        for k, v in features.items():
            try:
                fv = float(v)
                # Check for NaN, inf, -inf and convert to 0
                cleaned_features[k] = 0.0 if (np.isnan(fv) or np.isinf(fv)) else fv
            except (TypeError, ValueError):
                # If conversion fails, set to 0
                cleaned_features[k] = 0.0

        # Store prediction
        pred_obj = Prediction(
            model_id=model.id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            timestamp=datetime.utcnow(),
            signal=prediction['signal'],
            confidence=prediction['confidence'],
            probability_buy=prediction.get('probability_buy', 0),
            probability_sell=prediction.get('probability_sell', 0),
            probability_hold=prediction.get('probability_hold', 0),
            features_used=cleaned_features
        )
        db.add(pred_obj)
        db.commit()

        signal_type = prediction['signal'].upper() if isinstance(prediction['signal'], str) else str(prediction['signal']).upper()

        if signal_type == 'HOLD':
            raise HTTPException(status_code=404, detail=f"No actionable signal for {request.symbol} {request.timeframe}")

        # ── ATR from features ──────────────────────────────────────────────
        _last_close = float(db.query(TrainingData).filter(
            TrainingData.symbol == request.symbol,
            TrainingData.timeframe == request.timeframe
        ).order_by(TrainingData.timestamp.desc()).first().close)

        volatility_atr = cleaned_features.get("volatility_atr", 0)
        atr = float(volatility_atr) * _last_close if volatility_atr else None

        entry_price = None
        stop_loss   = None
        tp1 = tp2 = tp3 = None
        regime_name = None
        regime_adx  = None
        regime_conf = None

        if signal_type in ['BUY', 'SELL']:
            try:
                latest_data = db.query(TrainingData).filter(
                    TrainingData.symbol == request.symbol,
                    TrainingData.timeframe == request.timeframe
                ).order_by(TrainingData.timestamp.desc()).first()

                if latest_data:
                    # ── Fetch live price ───────────────────────────────────
                    try:
                        import httpx, os
                        twelve_key = os.environ.get('TWELVE_DATA_API_KEY')
                        if twelve_key:
                            resp = httpx.get(
                                'https://api.twelvedata.com/price',
                                params={'symbol': request.symbol, 'apikey': twelve_key},
                                timeout=5.0
                            )
                            if resp.status_code == 200:
                                live_price = float(resp.json().get('price', 0))
                                entry_price = live_price if live_price > 0 else float(latest_data.close)
                                logger.info(f"✅ [PRICE] Live price for {request.symbol}: {entry_price}")
                            else:
                                entry_price = float(latest_data.close)
                        else:
                            entry_price = float(latest_data.close)
                    except Exception as price_err:
                        entry_price = float(latest_data.close)
                        logger.warning(f"⚠️ [PRICE] Live price fetch failed: {price_err}")

                    # ── Regime detection ──────────────────────────────────
                    try:
                        regime_result = classify_regime_rules(cleaned_features)
                        regime_name = regime_result.regime_name
                        regime_adx  = regime_result.adx
                        regime_conf = regime_result.confidence
                        logger.info(f"🔍 [REGIME] {request.symbol} {request.timeframe}: {regime_name} (adx={regime_adx:.1f}, conf={regime_conf:.2f})")
                    except Exception as re:
                        logger.warning(f"⚠️ [REGIME] classify failed: {re}")
                        regime_result = RegimeResult(
                            regime=REGIME_RANGING, regime_name="UNKNOWN",
                            adx=20.0, choppiness=50.0, trend_direction=0,
                            confidence=0.5, allow_long=True, allow_short=True, notes="fallback"
                        )
                        regime_name = "UNKNOWN"
                        regime_adx  = 0.0
                        regime_conf = 0.5

                    # ── Regime-aware TP/SL ────────────────────────────────
                    if atr and atr > 0:
                        try:
                            # Ensure regime_result is a RegimeResult object
                            if regime_result is None or not isinstance(regime_result, RegimeResult):
                                regime_result = RegimeResult(
                                    regime=REGIME_RANGING, regime_name="UNKNOWN",
                                    adx=20.0, choppiness=50.0, trend_direction=0,
                                    confidence=0.5, allow_long=True, allow_short=True, notes="fallback"
                                )
                            
                            logger.debug(f"DEBUG [TP/SL] regime_result type: {type(regime_result)}, regime_result: {regime_result}")
                            tp_sl = calculate_tp_sl(
                                entry_price=entry_price,
                                atr=atr,
                                signal=signal_type,
                                regime=regime_result
                            )
                            stop_loss = tp_sl['stop_loss']
                            tp1       = tp_sl['take_profit_1']
                            tp2       = tp_sl['take_profit_2']
                            tp3       = tp_sl['take_profit_3']
                            logger.info(
                                f"✅ [TP/SL] {signal_type} {request.symbol} [{regime_name}]: "
                                f"Entry={entry_price}, SL={stop_loss}, "
                                f"TP1={tp1}, TP2={tp2}, TP3={tp3}"
                            )
                        except Exception as tpe:
                            logger.warning(f"⚠️ [TP/SL] regime_classifier failed: {tpe}, using flat multiples")
                            # Fallback to flat multiples
                            atr_sl = atr * 1.5
                            if signal_type == 'BUY':
                                stop_loss = entry_price - atr_sl
                                tp1 = entry_price + atr * 1.5
                                tp2 = entry_price + atr * 3.0
                                tp3 = entry_price + atr * 4.5
                            else:
                                stop_loss = entry_price + atr_sl
                                tp1 = entry_price - atr * 1.5
                                tp2 = entry_price - atr * 3.0
                                tp3 = entry_price - atr * 4.5
                    else:
                        # No ATR — percentage fallback
                        pct_sl = entry_price * 0.015
                        if signal_type == 'BUY':
                            stop_loss = entry_price - pct_sl
                            tp1 = entry_price + entry_price * 0.010
                            tp2 = entry_price + entry_price * 0.020
                            tp3 = entry_price + entry_price * 0.030
                        else:
                            stop_loss = entry_price + pct_sl
                            tp1 = entry_price - entry_price * 0.010
                            tp2 = entry_price - entry_price * 0.020
                            tp3 = entry_price - entry_price * 0.030

            except Exception as e:
                logger.error(f"❌ [TP/SL] Failed: {e}", exc_info=True)

        return {
            "symbol":            request.symbol,
            "timeframe":         request.timeframe,
            "signal":            prediction['signal'],
            "confidence":        prediction['confidence'],
            "probability_buy":   prediction.get('probability_buy', 0),
            "probability_sell":  prediction.get('probability_sell', 0),
            "probability_hold":  prediction.get('probability_hold', 0),
            "entry_price":       entry_price,
            "stop_loss":         stop_loss,
            "take_profit_1":     tp1,
            "take_profit_2":     tp2,
            "take_profit_3":     tp3,
            "atr":               atr,
            "regime":            regime_name,
            "regime_adx":        regime_adx,
            "regime_confidence": regime_conf,
            "pivot_support_1":   None,
            "pivot_resistance_1": None,
            "timestamp":         datetime.utcnow()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/models", response_model=List[ModelInfo])
async def list_models(
    symbol: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Model)
    if symbol:
        query = query.filter(Model.symbol == symbol)
    models = query.all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "symbol": m.symbol,
            "timeframe": m.timeframe,
            "version": m.version,
            "accuracy": m.accuracy,
            "is_active": m.is_active,
            "is_deployed": m.is_deployed,
            "trained_at": m.trained_at
        }
        for m in models
    ]


@app.get("/api/v1/models/{model_id}")
async def get_model(model_id: int, db: Session = Depends(get_db)):
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return {
        "id": model.id,
        "name": model.name,
        "symbol": model.symbol,
        "timeframe": model.timeframe,
        "version": model.version,
        "model_type": model.model_type,
        "accuracy": model.accuracy,
        "precision": model.precision,
        "recall": model.recall,
        "f1_score": model.f1_score,
        "is_active": model.is_active,
        "is_deployed": model.is_deployed,
        "trained_at": model.trained_at,
        "metadata": model.metadata
    }


@app.post("/api/v1/sync-data")
async def sync_market_data(
    symbols: List[str],
    timeframes: List[str] = ["5m", "15m", "30m", "1h", "4h", "1d", "1w"],
    background_tasks: BackgroundTasks = None
):
    try:
        if background_tasks:
            background_tasks.add_task(
                fetcher.sync_market_data,
                symbols=symbols,
                timeframes=timeframes
            )
        return {"message": "Data sync started", "symbols": symbols, "timeframes": timeframes, "status": "pending"}
    except Exception as e:
        logger.error(f"Data sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/status")
async def service_status(db: Session = Depends(get_db)):
    try:
        total_models    = db.query(Model).count()
        active_models   = db.query(Model).filter(Model.is_active == True).count()
        deployed_models = db.query(Model).filter(Model.is_deployed == True).count()
        total_predictions = db.query(Prediction).count()
        return {
            "service": "FreqAI Trading Signals",
            "status": "running",
            "timestamp": datetime.utcnow(),
            "statistics": {
                "total_models": total_models,
                "active_models": active_models,
                "deployed_models": deployed_models,
                "total_predictions": total_predictions
            }
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info(f"FreqAI server starting on {HOST}:{PORT}")
    init_db()
    logger.info("Database initialized")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FreqAI server shutting down")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=DEBUG, log_level="info")
