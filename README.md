# FreqAI Trading Signals Server

Standalone ML-powered trading signal generation service with separate database and server.

## Architecture

```
Django ASGI Server (:8000)
    ↓
FreqAI API Server (:9000) ← Separate Service
    ↓
FreqAI PostgreSQL Database
```

## Features

- **Market Data Fetching**: CCXT (crypto) + Yahoo Finance (stocks)
- **Feature Engineering**: 17+ technical indicators
- **Model Training**: RandomForest + GradientBoosting
- **Signal Generation**: Buy/Sell/Hold predictions
- **Model Management**: Version control + deployment
- **Async Processing**: Background training jobs

## Setup

### 1. Install Dependencies

```bash
cd FreqAIServer
bash setup.sh
source venv/bin/activate
```

### 2. Configure PostgreSQL

```bash
# Create database and user
sudo -u postgres psql

CREATE USER freqai_user WITH PASSWORD 'freqai_password';
CREATE DATABASE freqai_db OWNER freqai_user;
GRANT ALL PRIVILEGES ON DATABASE freqai_db TO freqai_user;
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 4. Initialize Database

```bash
python -c "from database import init_db; init_db()"
```

### 5. Run Server

```bash
python main.py
# Or with uvicorn directly:
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
```

## API Endpoints

### Health Check
```
GET /health
```

### Sync Market Data
```
POST /api/v1/sync-data
Body: {
  "symbols": ["BTC/USDT", "ETH/USDT"],
  "timeframes": ["1h", "4h", "1d"]
}
```

### Train Model
```
POST /api/v1/train
Body: {
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "limit": 100
}
```

### Get Prediction
```
POST /api/v1/predict
Body: {
  "symbol": "BTC/USDT",
  "timeframe": "1h"
}

Response:
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "signal": "buy",
  "confidence": 0.85,
  "probability_buy": 0.85,
  "probability_sell": 0.10,
  "probability_hold": 0.05,
  "timestamp": "2026-01-20T12:34:56"
}
```

### List Models
```
GET /api/v1/models
GET /api/v1/models?symbol=BTC/USDT
```

### Get Model Details
```
GET /api/v1/models/{model_id}
```

### Service Status
```
GET /api/v1/status
```

## Integration with Django

See [DJANGO_INTEGRATION.md](./DJANGO_INTEGRATION.md) for details on:
- Calling FreqAI from Django views
- Celery task integration
- Signal caching strategy
- Error handling

## Database Schema

### Models
- `training_data` - OHLCV historical data
- `models` - ML model metadata and versions
- `predictions` - Generated signal predictions
- `feature_cache` - Cached technical indicators
- `training_jobs` - Background training task tracking

## Performance Notes

- Model training happens in background (non-blocking)
- Predictions cached in Redis for fast delivery
- Separate database prevents main API slowdown
- Async market data fetching
- Feature caching reduces computation

## Development

### Run with Debug
```bash
FREQAI_DEBUG=True python main.py
```

### Run Tests
```bash
pytest tests/ -v
```

### Monitor Database
```bash
psql freqai_db
SELECT * FROM models;
SELECT * FROM predictions ORDER BY created_at DESC LIMIT 10;
```

## Troubleshooting

### Database Connection Error
```
Check PostgreSQL is running:
sudo systemctl status postgresql

Check credentials in .env
```

### Model Training Fails
```
Check training data exists:
SELECT COUNT(*) FROM training_data WHERE symbol = 'BTC/USDT';

Check logs in training_jobs table:
SELECT * FROM training_jobs ORDER BY created_at DESC;
```

### Predictions Return "hold"
```
Model may not be deployed:
SELECT * FROM models WHERE symbol = 'BTC/USDT' AND is_deployed = true;

Train a new model:
POST /api/v1/train with your symbol
```

## Future Enhancements

- [ ] Multiple model ensemble
- [ ] Hyperparameter optimization (Optuna)
- [ ] Real-time feature updates
- [ ] Model backtesting framework
- [ ] WebSocket for live predictions
- [ ] Docker containerization
- [ ] Kubernetes deployment
