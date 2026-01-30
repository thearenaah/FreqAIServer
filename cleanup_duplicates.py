#!/usr/bin/env python
"""
Clean up duplicate models from FreqAI database
Keeps only the latest version of each symbol/timeframe combination
"""
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

from config import DATABASE_URL
from database import Model, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_duplicates():
    """Remove duplicate models, keeping only latest version"""
    # Initialize database
    init_db()
    
    # Create session
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Get all symbol/timeframe combinations with duplicates
        duplicates = db.query(Model.symbol, Model.timeframe).group_by(
            Model.symbol, Model.timeframe
        ).all()
        
        logger.info(f"Checking {len(duplicates)} symbol/timeframe combinations...")
        
        deleted_count = 0
        for symbol, timeframe in duplicates:
            # Get all versions of this symbol/timeframe, ordered by version DESC
            models = db.query(Model).filter(
                Model.symbol == symbol,
                Model.timeframe == timeframe
            ).order_by(Model.version.desc()).all()
            
            if len(models) > 1:
                logger.info(f"Found {len(models)} versions of {symbol} {timeframe}")
                # Keep the latest (first in ordered list), delete the rest
                for old_model in models[1:]:
                    logger.info(f"  Deleting v{old_model.version}: {old_model.name} (id={old_model.id})")
                    db.delete(old_model)
                    deleted_count += 1
        
        db.commit()
        logger.info(f"✅ Cleanup complete! Deleted {deleted_count} duplicate model records")
        
        # Show final status
        total_models = db.query(Model).count()
        active_models = db.query(Model).filter(Model.is_active == True).count()
        deployed_models = db.query(Model).filter(Model.is_deployed == True).count()
        
        logger.info(f"📊 Final Status:")
        logger.info(f"   Total models: {total_models}")
        logger.info(f"   Active models: {active_models}")
        logger.info(f"   Deployed models: {deployed_models}")
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_duplicates()
