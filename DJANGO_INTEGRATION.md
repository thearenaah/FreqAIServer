# Django Integration with FreqAI Server

## Overview

Django communicates with FreqAI via HTTP REST API. All blocking operations (training, data sync) run as background Celery tasks.

## Architecture

```
Django View/API
    ↓
Celery Task (async)
    ↓
FreqAI HTTP Client
    ↓
FreqAI Server (:9000)
    ↓
FreqAI Database (PostgreSQL)
```

## 1. Add FreqAI Client to Django

Create `TheArena/freqai/client.py`:

```python
import httpx
import asyncio
from typing import Optional, Dict
from config import FREQAI_URL, FREQAI_TIMEOUT

class FreqAIClient:
    """HTTP client for FreqAI API"""
    
    def __init__(self, base_url: str = FREQAI_URL):
        self.base_url = base_url
        self.timeout = FREQAI_TIMEOUT
    
    async def health_check(self) -> bool:
        """Check if FreqAI is running"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=self.timeout)
                return response.status_code == 200
        except:
            return False
    
    async def train_model(self, symbol: str, timeframe: str) -> Dict:
        """Request model training"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/train",
                json={"symbol": symbol, "timeframe": timeframe},
                timeout=self.timeout
            )
            return response.json()
    
    async def predict(self, symbol: str, timeframe: str) -> Dict:
        """Get signal prediction"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/predict",
                json={"symbol": symbol, "timeframe": timeframe},
                timeout=self.timeout
            )
            return response.json()
    
    async def sync_data(self, symbols: list, timeframes: list = ["1h", "4h", "1d"]) -> Dict:
        """Sync market data"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync-data",
                json={"symbols": symbols, "timeframes": timeframes},
                timeout=self.timeout
            )
            return response.json()
    
    async def list_models(self, symbol: Optional[str] = None) -> list:
        """List available models"""
        async with httpx.AsyncClient() as client:
            params = {"symbol": symbol} if symbol else {}
            response = await client.get(
                f"{self.base_url}/api/v1/models",
                params=params,
                timeout=self.timeout
            )
            return response.json()
    
    async def service_status(self) -> Dict:
        """Get FreqAI service status"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/status",
                timeout=self.timeout
            )
            return response.json()


# Singleton instance
_client = None

def get_freqai_client() -> FreqAIClient:
    """Get FreqAI client instance"""
    global _client
    if _client is None:
        _client = FreqAIClient()
    return _client
```

## 2. Add Configuration

Update `TheArena/settings.py`:

```python
# FreqAI Configuration
FREQAI_URL = os.getenv("FREQAI_URL", "http://localhost:9000")
FREQAI_TIMEOUT = int(os.getenv("FREQAI_TIMEOUT", "30"))
FREQAI_ENABLED = os.getenv("FREQAI_ENABLED", "True") == "True"
```

## 3. Add Celery Tasks

Create `signals/tasks.py`:

```python
from celery import shared_task
from django.core.cache import cache
from freqai.client import get_freqai_client
import asyncio
import logging

logger = logging.getLogger(__name__)

@shared_task
def sync_market_data_task(symbols: list, timeframes: list = None):
    """Background task to sync market data"""
    if timeframes is None:
        timeframes = ["1h", "4h", "1d"]
    
    try:
        client = get_freqai_client()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(client.sync_data(symbols, timeframes))
        logger.info(f"Data sync completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Data sync failed: {e}")
        raise

@shared_task
def train_model_task(symbol: str, timeframe: str):
    """Background task to train new model"""
    try:
        client = get_freqai_client()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(client.train_model(symbol, timeframe))
        logger.info(f"Model training started: {result}")
        return result
    except Exception as e:
        logger.error(f"Model training failed: {e}")
        raise

@shared_task
def get_signal_prediction_task(symbol: str, timeframe: str):
    """Get signal prediction (can be cached)"""
    try:
        # Check cache first
        cache_key = f"signal_pred:{symbol}:{timeframe}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        client = get_freqai_client()
        loop = asyncio.get_event_loop()
        prediction = loop.run_until_complete(client.predict(symbol, timeframe))
        
        # Cache for 5 minutes
        cache.set(cache_key, prediction, 300)
        
        return prediction
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return {"signal": "hold", "confidence": 0.0}
```

## 4. Create Signals API Endpoint

Update `signals/api_views.py`:

```python
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .tasks import get_signal_prediction_task

class SignalPredictionView(generics.GenericAPIView):
    """Get AI-generated signal predictions"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        symbol = request.data.get('symbol')
        timeframe = request.data.get('timeframe', '1h')
        
        if not symbol:
            return Response(
                {'error': 'symbol required'},
                status=400
            )
        
        try:
            # Get prediction (can be from cache or async task)
            prediction = get_signal_prediction_task(symbol, timeframe)
            
            return Response({
                'symbol': symbol,
                'timeframe': timeframe,
                'signal': prediction.get('signal', 'hold'),
                'confidence': prediction.get('confidence', 0.0),
                'probability_buy': prediction.get('probability_buy', 0),
                'probability_sell': prediction.get('probability_sell', 0),
                'timestamp': prediction.get('timestamp')
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=500
            )
```

## 5. Scheduled Tasks (Celery Beat)

Create `TheArena/celery_beat_schedule.py`:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Sync market data every hour
    'sync-market-data-hourly': {
        'task': 'signals.tasks.sync_market_data_task',
        'schedule': crontab(minute=0),  # Every hour
        'args': (['BTC/USDT', 'ETH/USDT', 'AAPL', 'GOOGL'],)
    },
    
    # Retrain models daily
    'train-models-daily': {
        'task': 'signals.tasks.train_model_task',
        'schedule': crontab(hour=0, minute=0),  # Midnight
        'args': ('BTC/USDT', '1h')
    },
}
```

## 6. Error Handling

```python
# In views/tasks that use FreqAI

from freqai.client import get_freqai_client

async def safe_freqai_call(symbol, timeframe):
    """Safely call FreqAI with fallback"""
    try:
        client = get_freqai_client()
        
        # Check if FreqAI is available
        if not await client.health_check():
            logger.warning("FreqAI server unavailable")
            return get_fallback_signal(symbol)
        
        return await client.predict(symbol, timeframe)
    
    except Exception as e:
        logger.error(f"FreqAI error: {e}")
        return get_fallback_signal(symbol)

def get_fallback_signal(symbol):
    """Fallback signal when FreqAI unavailable"""
    return {
        "signal": "hold",
        "confidence": 0.0,
        "source": "fallback"
    }
```

## 7. Environment Variables

Add to `.env`:

```
# FreqAI
FREQAI_URL=http://localhost:9000
FREQAI_TIMEOUT=30
FREQAI_ENABLED=True

# Redis (for caching)
REDIS_URL=redis://localhost:6379/0
```

## 8. Testing

```python
# tests/test_freqai_integration.py

import pytest
from freqai.client import get_freqai_client

@pytest.mark.asyncio
async def test_freqai_health():
    client = get_freqai_client()
    is_healthy = await client.health_check()
    assert is_healthy

@pytest.mark.asyncio
async def test_freqai_prediction():
    client = get_freqai_client()
    prediction = await client.predict("BTC/USDT", "1h")
    
    assert "signal" in prediction
    assert "confidence" in prediction
    assert prediction["signal"] in ["buy", "sell", "hold"]
```

## Usage in Views

```python
# signals/views.py

from django.shortcuts import render
from .tasks import get_signal_prediction_task

def signal_detail_view(request, symbol, timeframe='1h'):
    """Display signal with AI prediction"""
    
    # Get prediction asynchronously
    prediction = get_signal_prediction_task(symbol, timeframe)
    
    context = {
        'signal': {
            'symbol': symbol,
            'timeframe': timeframe,
            'prediction': prediction,
            'generated_by': 'FreqAI'
        }
    }
    return render(request, 'signal_detail.html', context)
```

## Monitoring

Check FreqAI status from Django:

```python
# Django management command: python manage.py freqai_status

from django.core.management.base import BaseCommand
from freqai.client import get_freqai_client
import asyncio

class Command(BaseCommand):
    def handle(self, *args, **options):
        client = get_freqai_client()
        loop = asyncio.get_event_loop()
        
        status = loop.run_until_complete(client.service_status())
        self.stdout.write(self.style.SUCCESS(f"FreqAI Status: {status}"))
```
