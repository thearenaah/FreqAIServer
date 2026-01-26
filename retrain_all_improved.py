#!/usr/bin/env python3
"""
Retrain all models with improved aggressive label strategy
Uses better feature engineering + aggressive labeling for 80%+ accuracy
"""

import logging
import requests
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Models to retrain (deployed ones with lower accuracy)
MODELS_TO_RETRAIN = [
    # (symbol, timeframe)
    ('EUR/USD', '1h'), ('EUR/USD', '4h'),
    ('GBP/USD', '1h'), ('GBP/USD', '4h'),
    ('USD/JPY', '1h'), ('USD/JPY', '4h'),
    ('XAU/USD', '1h'), ('XAU/USD', '4h'),
    ('AUD/USD', '1h'), ('AUD/USD', '4h'),
    ('USD/CAD', '1h'), ('USD/CAD', '4h'),
    ('USD/CHF', '1h'), ('USD/CHF', '4h'),
    ('GBP/JPY', '1h'), ('GBP/JPY', '4h'),
    ('EUR/AUD', '1h'), ('EUR/AUD', '4h'),
    ('GBP/AUD', '1h'), ('GBP/AUD', '4h'),
    ('BTC/USD', '1h'), ('BTC/USD', '4h'),
    ('ETH/USD', '1h'), ('ETH/USD', '4h'),
    ('LTC/USD', '1h'), ('LTC/USD', '4h'),
]

print("\n" + "="*80)
print("🚀 RETRAINING ALL MODELS WITH IMPROVED LABELS")
print("="*80 + "\n")

print(f"📊 Retraining {len(MODELS_TO_RETRAIN)} models with aggressive labels...")
print(f"   - Better feature engineering (35+ indicators)")
print(f"   - Aggressive labeling (1.5% threshold, 1.1x ratio)")
print(f"   - Balanced class weights")
print(f"   - Stratified train/test split\n")

training_jobs = []
failed = []

for symbol, timeframe in MODELS_TO_RETRAIN:
    try:
        payload = {
            'symbol': symbol,
            'timeframe': timeframe,
            'epochs': 100,
            'batch_size': 32,
            'version': 2,  # v2 = with improved labels
        }
        
        response = requests.post(
            'http://localhost:9000/api/v1/train',
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id', 'unknown')
            print(f"✅ {symbol:12} {timeframe:3}  Job {job_id}")
            training_jobs.append((symbol, timeframe, job_id))
        else:
            print(f"⚠️  {symbol:12} {timeframe:3}  API error: {response.status_code}")
            failed.append((symbol, timeframe))
    except Exception as e:
        print(f"⚠️  {symbol:12} {timeframe:3}  Error: {str(e)[:40]}")
        failed.append((symbol, timeframe))

print(f"\n✅ Queued {len(training_jobs)} training jobs")
if failed:
    print(f"⚠️  Failed to queue {len(failed)} jobs")

print(f"\n⏳ Waiting 120 seconds for training to complete...")
time.sleep(120)

# Check results
print(f"\n{'='*80}")
print("PHASE 3: ACCURACY CHECK (After Improved Training)")
print(f"{'='*80}\n")

try:
    response = requests.get('http://localhost:9000/api/v1/models', timeout=10)
    if response.status_code == 200:
        models = response.json()
        
        # Filter to our models
        our_models = [m for m in models if any(
            m['symbol'] == s and m['timeframe'] == t 
            for s, t in MODELS_TO_RETRAIN
        ) and m['is_deployed']]
        
        print(f"{'Symbol':<12} {'TF':<6} {'Accuracy':<12} {'Status':<20} {'Version'}")
        print("-"*80)
        
        accuracies = []
        for model in sorted(our_models, key=lambda x: (x['symbol'], x['timeframe'])):
            if model['accuracy'] is not None:
                acc = model['accuracy']
                accuracies.append(acc)
                
                if acc >= 0.80:
                    status = "✅✅ TARGET MET"
                elif acc >= 0.75:
                    status = "✅ Very Good"
                elif acc >= 0.70:
                    status = "✅ Good"
                elif acc >= 0.60:
                    status = "⚠️  Fair"
                else:
                    status = "❌ Poor"
                
                version = model.get('version', 1)
                print(f"{model['symbol']:<12} {model['timeframe']:<6} {acc:.1%}        {status:<20} v{version}")
        
        if accuracies:
            avg = sum(accuracies) / len(accuracies)
            print("\n" + "="*80)
            print(f"📊 RESULTS")
            print("="*80)
            print(f"Average Accuracy:   {avg:.1%}")
            print(f"Models @ 80%+:      {sum(1 for a in accuracies if a >= 0.80)}/{len(accuracies)}")
            print(f"Models @ 75%+:      {sum(1 for a in accuracies if a >= 0.75)}/{len(accuracies)}")
            print(f"Models @ 70%+:      {sum(1 for a in accuracies if a >= 0.70)}/{len(accuracies)}")
            print(f"Best Model:         {max(accuracies):.1%}")
            print(f"Worst Model:        {min(accuracies):.1%}")
            
            if avg >= 0.80:
                print(f"\n🎉 TARGET ACHIEVED: 80%+ average accuracy!")
            elif avg >= 0.75:
                print(f"\n⭐ Very Good! Close to target (75%+ avg)")
            elif avg >= 0.70:
                print(f"\n📈 Improving... (70%+ avg)")
            
            print("="*80 + "\n")
        
except Exception as e:
    print(f"Error checking models: {e}")

