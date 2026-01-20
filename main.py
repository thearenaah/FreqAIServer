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
from config import HOST, PORT, DEBUG
from market_data import MarketDataFetcher
from features import FeatureEngineer
from models import ModelTrainer

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
    allow_origins=["*"],
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
    symbol: str
    timeframe: str
    signal: str  # buy, sell, hold
    confidence: float
    probability_buy: float
    probability_sell: float
    probability_hold: float
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
        # Create or get model
        model = db.query(Model).filter(
            Model.symbol == request.symbol,
            Model.timeframe == request.timeframe,
            Model.is_active == True
        ).first()
        
        if not model:
            model = Model(
                name=f"{request.symbol}_{request.timeframe}_v1",
                symbol=request.symbol,
                timeframe=request.timeframe,
                version=1,
                trained_at=datetime.utcnow(),
                model_path=f"./models/{request.symbol}_{request.timeframe}.pkl"
            )
            db.add(model)
            db.commit()
            db.refresh(model)
        
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
            "status": "pending"
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
        # Get active model
        model = db.query(Model).filter(
            Model.symbol == request.symbol,
            Model.timeframe == request.timeframe,
            Model.is_deployed == True
        ).first()
        
        if not model:
            raise HTTPException(
                status_code=404,
                detail=f"No active model for {request.symbol} {request.timeframe}"
            )
        
        # Get prediction
        prediction = trainer.predict(model, db)
        
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
            features_used=prediction.get('features', {})
        )
        db.add(pred_obj)
        db.commit()
        
        return {
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "signal": prediction['signal'],
            "confidence": prediction['confidence'],
            "probability_buy": prediction.get('probability_buy', 0),
            "probability_sell": prediction.get('probability_sell', 0),
            "probability_hold": prediction.get('probability_hold', 0),
            "timestamp": datetime.utcnow()
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
        debug=DEBUG,
        log_level="info"
    )
