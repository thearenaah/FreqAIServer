# FreqAI Integration - Complete Setup Guide

## What's Been Created

### 1. **FreqAI Server** (`/FreqAIServer/`)
Standalone FastAPI service with separate PostgreSQL database

**Files Created:**
- `main.py` - FastAPI application with REST endpoints
- `database.py` - SQLAlchemy models for FreqAI database
- `models.py` - ML model training and prediction
- `features.py` - Feature engineering with 17+ indicators
- `market_data.py` - Market data fetching (CCXT + Yahoo Finance)
- `config.py` - Configuration management
- `requirements.txt` - Python dependencies
- `README.md` - Setup and API documentation
- `DJANGO_INTEGRATION.md` - Integration guide with Django
- `.env.example` - Environment template
- `setup.sh` - Installation script

### 2. **Key Features**

✅ **API Endpoints:**
- POST `/api/v1/train` - Train ML model (background)
- POST `/api/v1/predict` - Get signal prediction
- GET `/api/v1/models` - List models
- POST `/api/v1/sync-data` - Fetch market data
- GET `/api/v1/status` - Service status

✅ **ML Models:**
- RandomForest classifier
- GradientBoosting classifier
- Model versioning & deployment
- Accuracy tracking

✅ **Features (17+):**
- SMA (20, 50, 200)
- RSI, MACD, Bollinger Bands
- ATR, Volume indicators
- Price change & volatility
- Return statistics

✅ **Data Sources:**
- CCXT (100+ crypto exchanges)
- Yahoo Finance (stocks, ETFs)

✅ **Database:**
- Separate PostgreSQL instance
- Training data storage
- Model metadata
- Prediction history
- Feature caching

## Installation Steps

### 1. Create FreqAI Database

```bash
sudo -u postgres psql

CREATE USER freqai_user WITH PASSWORD 'freqai_password';
CREATE DATABASE freqai_db OWNER freqai_user;
GRANT ALL PRIVILEGES ON DATABASE freqai_db TO freqai_user;
\q
```

### 2. Setup FreqAI Server

```bash
cd /home/soarer/Documents/projects/Arena/FreqAIServer
bash setup.sh
source venv/bin/activate
cp .env.example .env
# Edit .env with your PostgreSQL details
```

### 3. Initialize FreqAI Database

```bash
python -c "from database import init_db; init_db()"
```

### 4. Start FreqAI Server

```bash
python main.py
# Server runs on http://localhost:9000
```

### 5. Setup Django Integration

In Django project (`/TheArena/`):

```bash
# Add environment variables to .env
echo "FREQAI_URL=http://localhost:9000" >> .env
echo "FREQAI_TIMEOUT=30" >> .env
echo "FREQAI_ENABLED=True" >> .env

# Install FreqAI client module (copy from FreqAIServer/)
mkdir -p TheArena/freqai
cp FreqAIServer/client.py TheArena/freqai/
```

### 6. Configure Celery Tasks

In Django, create `signals/tasks.py` with async tasks (see DJANGO_INTEGRATION.md)

## Architecture Overview

```
┌─────────────────────────────────────────┐
│   Django ASGI Server (Port 8000)       │
│   - User Management                     │
│   - Trade Journal                       │
│   - Signal Delivery                     │
│   - Redis Cache                         │
└──────────────────┬──────────────────────┘
                   │ HTTP API Calls
                   ↓ (Async via Celery)
┌─────────────────────────────────────────┐
│   FreqAI Server (Port 9000)             │
│   - FastAPI REST API                    │
│   - Model Training                      │
│   - Signal Generation                   │
│   - Market Data Sync                    │
└──────────────────┬──────────────────────┘
                   │ SQL Queries
                   ↓
┌─────────────────────────────────────────┐
│   FreqAI PostgreSQL Database            │
│   - Training Data (OHLCV)               │
│   - Model Metadata                      │
│   - Predictions                         │
│   - Feature Cache                       │
└─────────────────────────────────────────┘
```

## API Usage Examples

### Sync Market Data
```bash
curl -X POST http://localhost:9000/api/v1/sync-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "timeframes": ["1h", "4h", "1d"]
  }'
```

### Train Model
```bash
curl -X POST http://localhost:9000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "timeframe": "1h"
  }'
```

### Get Prediction
```bash
curl -X POST http://localhost:9000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "timeframe": "1h"
  }'

Response:
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "signal": "buy",
  "confidence": 0.87,
  "probability_buy": 0.87,
  "probability_sell": 0.08,
  "probability_hold": 0.05,
  "timestamp": "2026-01-20T12:34:56"
}
```

## Django Integration Code

### 1. Client Module
```python
# TheArena/freqai/client.py
from config import FREQAI_URL, FREQAI_TIMEOUT

class FreqAIClient:
    async def predict(self, symbol, timeframe) -> dict:
        # Returns prediction with signal, confidence, probabilities
    
    async def train_model(self, symbol, timeframe) -> dict:
        # Request background model training
    
    async def sync_data(self, symbols, timeframes) -> dict:
        # Fetch market data
```

### 2. Celery Tasks
```python
# signals/tasks.py
@shared_task
def get_signal_prediction_task(symbol, timeframe):
    # Cache predictions for 5 minutes
    # Fallback to "hold" if FreqAI unavailable

@shared_task
def sync_market_data_task(symbols, timeframes):
    # Run market data sync in background

@shared_task
def train_model_task(symbol, timeframe):
    # Train new model in background
```

### 3. API Endpoint
```python
# signals/api_views.py
class SignalPredictionView(generics.GenericAPIView):
    def post(self, request):
        # Returns AI-generated signal prediction
```

## Monitoring & Debugging

### Check FreqAI Status
```bash
curl http://localhost:9000/health
curl http://localhost:9000/api/v1/status
```

### Database Queries
```bash
psql freqai_db

# List models
SELECT * FROM models;

# Check predictions
SELECT * FROM predictions ORDER BY created_at DESC LIMIT 10;

# Check training data
SELECT COUNT(*) as count, symbol, timeframe FROM training_data 
GROUP BY symbol, timeframe;
```

### Check Logs
```bash
# FreqAI server logs (if running in foreground)
tail -f freqai_server.log

# Django logs for FreqAI integration
tail -f TheArena/logs/signals.log
```

## Production Deployment

### 1. Docker
```dockerfile
# Dockerfile for FreqAI
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

### 2. Systemd Service
```ini
[Unit]
Description=FreqAI Trading Signals Server
After=network.target postgresql.service

[Service]
Type=simple
User=trading
WorkingDirectory=/opt/freqai
ExecStart=/opt/freqai/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Nginx Proxy
```nginx
upstream freqai {
    server localhost:9000;
}

server {
    listen 443 ssl;
    server_name freqai.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/freqai.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/freqai.yourdomain.com/privkey.pem;
    
    location / {
        proxy_pass http://freqai;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Next Steps

1. **Test FreqAI Server**
   - Start server: `python main.py`
   - Check health: `curl http://localhost:9000/health`
   - Sync data: POST to `/api/v1/sync-data`
   - Train model: POST to `/api/v1/train`

2. **Integrate with Django**
   - Copy FreqAI client to Django
   - Create Celery tasks
   - Add API endpoint
   - Configure environment

3. **Frontend Integration**
   - Create prediction display in React
   - Show confidence levels
   - Display probabilities

4. **Monitoring**
   - Set up logging
   - Create dashboards
   - Monitor model accuracy

## Support

See:
- `README.md` - Server setup and API docs
- `DJANGO_INTEGRATION.md` - Django integration guide
- Source files for detailed implementation
