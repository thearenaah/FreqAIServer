"""
Database configuration and models for FreqAI server
Uses separate PostgreSQL database from main Django app
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

from config import DATABASE_URL

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connection health
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TrainingData(Base):
    """Store market data for model training"""
    __tablename__ = "training_data"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10))  # 1m, 5m, 1h, 4h, 1d
    timestamp = Column(DateTime, index=True)
    
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    
    # Technical indicators
    indicators = Column(JSON)  # Store calculated indicators
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Model(Base):
    """Store model metadata and versions"""
    __tablename__ = "models"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10))
    
    version = Column(Integer, default=1)
    model_type = Column(String(50))  # RandomForest, GradientBoosting, etc.
    
    accuracy = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    
    is_active = Column(Boolean, default=False)
    is_deployed = Column(Boolean, default=False)
    
    trained_at = Column(DateTime, index=True)
    last_prediction_at = Column(DateTime, nullable=True)
    
    model_path = Column(String(255))  # Path to saved model file
    metadata = Column(JSON)  # Store model hyperparameters
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Prediction(Base):
    """Store model predictions for signals"""
    __tablename__ = "predictions"
    
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, index=True)
    
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10))
    timestamp = Column(DateTime, index=True)
    
    signal = Column(String(10))  # buy, sell, hold
    confidence = Column(Float)  # 0.0-1.0
    
    # Additional prediction details
    probability_buy = Column(Float, nullable=True)
    probability_sell = Column(Float, nullable=True)
    probability_hold = Column(Float, nullable=True)
    
    features_used = Column(JSON)  # Store feature values for debugging
    
    # Outcome tracking (after actual market movement)
    actual_signal = Column(String(10), nullable=True)  # What actually happened
    outcome = Column(String(20), nullable=True)  # correct, incorrect, neutral
    
    created_at = Column(DateTime, default=datetime.utcnow)


class FeatureCache(Base):
    """Cache computed features to avoid recalculation"""
    __tablename__ = "feature_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10), index=True)
    timestamp = Column(DateTime, index=True)
    
    features = Column(JSON)  # All computed features
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, index=True)  # Auto-expire old features


class TrainingJob(Base):
    """Track model training jobs"""
    __tablename__ = "training_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, index=True)
    
    status = Column(String(20))  # pending, running, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# Create all tables
def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
