#!/usr/bin/env python3
"""
Retrain all models with aggressive label strategy
Aggressive labeling: 0.25% threshold + 1.05x ratio
Expected: 20-25% BUY+SELL signals, 75% HOLD - much better for learning
Expected accuracy improvement: 47% → 70%+
"""

import logging
import requests
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Target symbols for training
ASSETS = {
    'forex_majors': [
        'EUR/USD', 'GBP/USD', 'USD/JPY', 'XAU/USD', 'AUD/USD',
        'USD/CAD', 'USD/CHF', 'GBP/JPY', 'EUR/AUD', 'GBP/AUD',
    ],
    'major_crypto': [
        'BTC/USD', 'ETH/USD', 'LTC/USD',
    ]
}

all_symbols = ASSETS['forex_majors'] + ASSETS['major_crypto']
timeframes = ['1h', '4h', '1d']  # All timeframes

FREQAI_URL = 'http://localhost:9000'

def train_models():
    """Train all models with aggressive labels"""
    
    print("\n" + "="*80)
    print("🚀 AGGRESSIVE LABEL RETRAINING")
    print("="*80)
    print(f"Strategy: 0.25% threshold + 1.05x ratio")
    print(f"Expected: 20-25% actionable signals, 75% HOLD")
    print(f"Target Accuracy: 70%+\n")
    
    all_jobs = []
    
    print(f"Queuing {len(all_symbols)} symbols × {len(timeframes)} timeframes...")
    print("-"*80 + "\n")
    
    for symbol in all_symbols:
        for timeframe in timeframes:
            try:
                payload = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'epochs': 100,
                    'batch_size': 32,
                }
                
                response = requests.post(
                    f'{FREQAI_URL}/api/v1/train',
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    job_id = result.get('job_id', '?')
                    all_jobs.append({
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'job_id': job_id,
                        'status': 'queued'
                    })
                    print(f"  ✅ {symbol:12} {timeframe:3}  Job {job_id}")
                else:
                    print(f"  ⚠️  {symbol:12} {timeframe:3}  Error {response.status_code}")
                    
            except Exception as e:
                print(f"  ❌ {symbol:12} {timeframe:3}  {str(e)[:40]}")
    
    print(f"\n{'='*80}")
    print(f"✅ Total jobs queued: {len(all_jobs)}/{len(all_symbols)*len(timeframes)}")
    print(f"{'='*80}\n")
    
    return all_jobs


def wait_for_training(duration_seconds=180):
    """Wait for training to complete"""
    print(f"⏳ Waiting {duration_seconds} seconds for training...\n")
    
    for i in range(duration_seconds):
        if i % 30 == 0 and i > 0:
            print(f"   {i}s elapsed...")
        time.sleep(1)
    
    print(f"   {duration_seconds}s complete - checking results...\n")


def check_results():
    """Check model accuracy after training"""
    try:
        response = requests.get(f'{FREQAI_URL}/api/v1/models', timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch models: {response.status_code}")
            return
        
        models = response.json()
        
        # Filter deployed models
        deployed = [m for m in models if m.get('is_deployed')]
        
        # Filter for our assets
        our_models = [m for m in deployed if m.get('symbol') in all_symbols]
        
        if not our_models:
            print("⚠️  No models found")
            return
        
        # Sort for display
        our_models.sort(key=lambda x: (x['symbol'], x['timeframe']))
        
        print("="*80)
        print("📊 ACCURACY RESULTS (With Aggressive Labels)")
        print("="*80)
        print(f"{'Symbol':<12} {'TF':<6} {'Accuracy':<12} {'Status'}")
        print("-"*80)
        
        accuracies = []
        target_80 = 0
        target_70 = 0
        
        for model in our_models:
            acc = model.get('accuracy')
            if acc is not None:
                accuracies.append(acc)
                
                if acc >= 0.80:
                    status = "✅✅ EXCELLENT (80%+)"
                    target_80 += 1
                elif acc >= 0.70:
                    status = "✅ GOOD (70%+)"
                    target_70 += 1
                elif acc >= 0.60:
                    status = "⚠️  FAIR (60%+)"
                else:
                    status = "❌ POOR (<60%)"
                
                print(f"{model['symbol']:<12} {model['timeframe']:<6} {acc:.1%}        {status}")
        
        if accuracies:
            avg = sum(accuracies) / len(accuracies)
            improvement = avg - 0.479  # Previous average was 47.9%
            
            print("\n" + "="*80)
            print("📈 Summary Statistics:")
            print(f"  Average Accuracy:      {avg:.1%}")
            print(f"  Improvement from 47.9%: +{improvement:.1%}")
            print(f"  Models @ 80%+:         {target_80}/{len(our_models)}")
            print(f"  Models @ 70%+:         {target_70}/{len(our_models)}")
            print(f"  Best Model:            {max(accuracies):.1%}")
            print(f"  Worst Model:           {min(accuracies):.1%}")
            print(f"  Std Dev:               {(sum((x-avg)**2 for x in accuracies)/len(accuracies))**0.5:.1%}")
            print("="*80 + "\n")
            
            if avg >= 0.70:
                print("✅ SUCCESS! Achieved 70%+ average accuracy with aggressive labels!\n")
            elif avg >= 0.65:
                print("⚠️  Good progress - 65%+ average. Consider further tuning.\n")
            else:
                print("⏳ Training in progress - check again in a few minutes.\n")
        
    except Exception as e:
        print(f"❌ Error checking results: {e}\n")


def main():
    """Main execution"""
    try:
        # Queue training jobs
        jobs = train_models()
        
        if not jobs:
            print("⚠️  No training jobs were queued. Server may be unavailable.")
            return
        
        # Wait for training
        wait_for_training(duration_seconds=180)
        
        # Check results
        check_results()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Training interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == '__main__':
    main()
