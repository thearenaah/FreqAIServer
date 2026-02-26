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

from database import init_db, get_db, Model, Prediction, TrainingData, TrainingJob
from config import HOST, PORT, DEBUG, ALLOWED_ORIGINS
from market_data import MarketDataFetcher
from features import FeatureEngineer
from models import ModelTrainer
from risk_management import RiskManagement, RiskManagementConfig

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
    signal: str  # buy, sell, hold
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
    """Health check endpoint"""
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
    """
    Train a new model for a symbol/timeframe
    Runs in background to avoid blocking
    """
    try:
        # Sanitize symbol for file path (replace / with _)
        safe_symbol = request.symbol.replace('/', '_')
        model_path = f"./models/{safe_symbol}_{request.timeframe}_model.pkl"
        
        # Check if model exists (by symbol + timeframe, not name)
        existing_model = db.query(Model).filter(
            Model.symbol == request.symbol,
            Model.timeframe == request.timeframe
        ).first()
        
        if existing_model:
            # Update existing model - increment version
            model = existing_model
            model.version += 1
            model.trained_at = datetime.utcnow()
            model.name = f"{request.symbol}_{request.timeframe}_v{model.version}"
            model.model_path = model_path
            model.is_active = False  # Mark as not ready until training completes
            model.is_deployed = False
            db.commit()
            db.refresh(model)
            logger.info(f"Updating model {model.id} to version {model.version}")
        else:
            # Create new model
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
        
        # Create training job
        job = TrainingJob(model_id=model.id, status="pending")
        db.add(job)
        db.commit()
        
        # Queue background task
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
    """
    Get signal prediction for a symbol/timeframe
    """
    try:
        # Get active models, ordered by accuracy (highest first)
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
        
        # Use model with highest accuracy
        model = models[0]
        
        # Get prediction - this will raise if model file missing or data insufficient
        try:
            prediction = trainer.predict(model, db)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        
        # Clean features (remove NaN values for JSON storage)
        features = prediction.get('features', {})
        cleaned_features = {}
        for k, v in features.items():
            if v is not None and not (isinstance(v, float) and (v != v or v == float('inf') or v == float('-inf'))):
                cleaned_features[k] = v
            else:
                cleaned_features[k] = 0  # Replace NaN/Inf with 0
        
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
        
        # Calculate TP/SL using risk management if signal is actionable
        entry_price = None
        stop_loss = None
        tp1 = None
        tp2 = None
        tp3 = None
        atr = None
        pivot_s1 = None
        pivot_r1 = None
        
        signal_type = prediction['signal'].upper() if isinstance(prediction['signal'], str) else str(prediction['signal']).upper()
        
        # Return 404 if no actionable signal
        if signal_type == 'HOLD':
            raise HTTPException(status_code=404, detail=f"No actionable signal for {request.symbol} {request.timeframe}")
        if signal_type in ['BUY', 'SELL']:
            try:
                # Use current close price as entry
                latest_data = db.query(TrainingData).filter(
                    TrainingData.symbol == request.symbol,
                    TrainingData.timeframe == request.timeframe
                ).order_by(TrainingData.timestamp.desc()).first()
                
                if latest_data:
                    entry_price = float(latest_data.close)
                    
                    # Extract features for risk management
                    features = cleaned_features
                    atr_val = features.get('atr_14', None)
                    atr = float(atr_val) if atr_val is not None else None
                    
                    # Get pivot points
                    pivot_data = prediction.get('pivot_points', {})
                    pivot_s1 = pivot_data.get('s1', None)
                    pivot_r1 = pivot_data.get('r1', None)
                    
                    # Initialize risk manager
                    rm_config = RiskManagementConfig(
                        tp1_risk_reward=1.0,
                        tp2_risk_reward=2.0,
                        tp3_risk_reward=3.0,
                    )
                    risk_manager = RiskManagement(rm_config)
                    
                    # Get support/resistance from features
                    support_level = features.get('ema_50', entry_price * 0.99) or (entry_price * 0.99)
                    resistance_level = features.get('ema_200', entry_price * 1.01) or (entry_price * 1.01)
                    
                    # Convert to float if needed
                    support_level = float(support_level) if support_level is not None else (entry_price * 0.99)
                    resistance_level = float(resistance_level) if resistance_level is not None else (entry_price * 1.01)
                    
                    # Calculate SL/TP based on direction
                    if signal_type == 'BUY':
                        trade_levels = risk_manager.calculate_long_trade_levels(
                            entry_price=entry_price,
                            support_level=support_level,
                            pivot_data=pivot_data or {},
                            atr=atr,
                        )
                        if trade_levels and 'error' not in trade_levels:
                            stop_loss = float(trade_levels.get('stop_loss', entry_price * 0.95))
                            tp1_obj = trade_levels.get('tp1')
                            tp2_obj = trade_levels.get('tp2')
                            tp3_obj = trade_levels.get('tp3')
                            tp1 = float(tp1_obj.get('price')) if tp1_obj else None
                            tp2 = float(tp2_obj.get('price')) if tp2_obj else None
                            tp3 = float(tp3_obj.get('price')) if tp3_obj else None
                            logger.info(f"✅ [TP/SL] BUY {request.symbol}: Entry={entry_price}, SL={stop_loss}, TP1={tp1}, TP2={tp2}, TP3={tp3}")
                        else:
                            logger.warning(f"⚠️ [TP/SL] BUY trade_levels error: {trade_levels}")
                    else:  # SELL
                        trade_levels = risk_manager.calculate_short_trade_levels(
                            entry_price=entry_price,
                            resistance_level=resistance_level,
                            pivot_data=pivot_data or {},
                            atr=atr,
                        )
                        if trade_levels and 'error' not in trade_levels:
                            stop_loss = float(trade_levels.get('stop_loss', entry_price * 1.05))
                            tp1_obj = trade_levels.get('tp1')
                            tp2_obj = trade_levels.get('tp2')
                            tp3_obj = trade_levels.get('tp3')
                            tp1 = float(tp1_obj.get('price')) if tp1_obj else None
                            tp2 = float(tp2_obj.get('price')) if tp2_obj else None
                            tp3 = float(tp3_obj.get('price')) if tp3_obj else None
                            logger.info(f"✅ [TP/SL] SELL {request.symbol}: Entry={entry_price}, SL={stop_loss}, TP1={tp1}, TP2={tp2}, TP3={tp3}")
                        else:
                            logger.warning(f"⚠️ [TP/SL] SELL trade_levels error: {trade_levels}")
                else:
                    logger.warning(f"⚠️ [TP/SL] No training data for {request.symbol} {request.timeframe}")
            except Exception as e:
                logger.error(f"❌ [TP/SL] Failed to calculate TP/SL: {e}", exc_info=True)
                # Continue without TP/SL if calculation fails
        
        # DEBUG: Log return values
        logger.info(f"DEBUG: Returning entry_price={entry_price}, stop_loss={stop_loss}, tp1={tp1}, tp2={tp2}, tp3={tp3}")
        
        response_dict = {
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "signal": prediction['signal'],
            "confidence": prediction['confidence'],
            "probability_buy": prediction.get('probability_buy', 0),
            "probability_sell": prediction.get('probability_sell', 0),
            "probability_hold": prediction.get('probability_hold', 0),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit_3": tp3,
            "atr": atr,
            "pivot_support_1": pivot_s1,
            "pivot_resistance_1": pivot_r1,
            "timestamp": datetime.utcnow()
        }
        logger.info(f"DEBUG: Response dict keys: {response_dict.keys()}")
        return response_dict
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
    """List all models or filter by symbol"""
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
async def get_model(
    model_id: int,
    db: Session = Depends(get_db)
):
    """Get specific model details"""
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
    timeframes: List[str] = ["1h", "4h", "1d"],
    background_tasks: BackgroundTasks = None
):
    """
    Sync market data for symbols
    Runs in background
    """
    try:
        if background_tasks:
            background_tasks.add_task(
                fetcher.sync_market_data,
                symbols=symbols,
                timeframes=timeframes
            )
        
        return {
            "message": "Data sync started",
            "symbols": symbols,
            "timeframes": timeframes,
            "status": "pending"
        }
    except Exception as e:
        logger.error(f"Data sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/status")
async def service_status(db: Session = Depends(get_db)):
    """Get service status and statistics"""
    try:
        total_models = db.query(Model).count()
        active_models = db.query(Model).filter(Model.is_active == True).count()
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
    """Initialize on startup"""
    logger.info(f"FreqAI server starting on {HOST}:{PORT}")
    init_db()
    logger.info("Database initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("FreqAI server shutting down")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info"
    )
