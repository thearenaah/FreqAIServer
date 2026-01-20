"""
FreqAI Server - Machine Learning predictions for trading signals
Separate service from Django to avoid blocking the main API
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv(
    "FREQAI_DATABASE_URL",
    "postgresql://freqai_user:freqai_pass@localhost:5432/freqai_db"
)

# Server
HOST = os.getenv("FREQAI_HOST", "0.0.0.0")
PORT = int(os.getenv("FREQAI_PORT", "9000"))
DEBUG = os.getenv("FREQAI_DEBUG", "False") == "True"

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")

# Market Data
CCXT_EXCHANGE = os.getenv("CCXT_EXCHANGE", "binance")
FEATURE_WINDOW = int(os.getenv("FEATURE_WINDOW", "20"))
TRAINING_WINDOW = int(os.getenv("TRAINING_WINDOW", "100"))

# Model
MODEL_PATH = os.getenv("MODEL_PATH", "./models")
MAX_MODELS = int(os.getenv("MAX_MODELS", "10"))
RETRAIN_INTERVAL_HOURS = int(os.getenv("RETRAIN_INTERVAL_HOURS", "24"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
