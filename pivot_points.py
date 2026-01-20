"""
Pivot Points Calculation (Baby Pips Methodology)
https://www.babypips.com/forexschool/kindergarten/pivot-points
"""
import numpy as np
import pandas as pd
from typing import Dict


class PivotPoints:
    """Calculate support and resistance levels using pivot points"""
    
    @staticmethod
    def calculate_floor_pivot(high: float, low: float, close: float) -> Dict[str, float]:
        """
        Floor Pivot Points (Most Common)
        
        Pivot = (H + L + C) / 3
        R1 = (2 * Pivot) - Low
        R2 = Pivot + (High - Low)
        S1 = (2 * Pivot) - High
        S2 = Pivot - (High - Low)
        
        Extreme (R3/S3):
        R3 = High + 2(Pivot - Low)
        S3 = Low - 2(High - Pivot)
        """
        pivot = (high + low + close) / 3
        
        r1 = (2 * pivot) - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        
        s1 = (2 * pivot) - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)
        
        return {
            'pivot': pivot,
            'r1': r1,      # First resistance
            'r2': r2,      # Second resistance
            'r3': r3,      # Strong resistance
            's1': s1,      # First support
            's2': s2,      # Second support
            's3': s3,      # Strong support
        }
    
    @staticmethod
    def calculate_camarilla_pivot(high: float, low: float, close: float) -> Dict[str, float]:
        """
        Camarilla Pivot Points
        More sensitive than floor pivots, good for intraday
        
        H4 = Close + 1.1 * (High - Low) / 2
        H3 = Close + 1.1 * (High - Low) / 4
        H2 = Close + 1.1 * (High - Low) / 6
        H1 = Close + 1.1 * (High - Low) / 12
        
        Similar for L1-L4 (support)
        """
        hl_range = high - low
        
        h4 = close + 1.1 * hl_range / 2
        h3 = close + 1.1 * hl_range / 4
        h2 = close + 1.1 * hl_range / 6
        h1 = close + 1.1 * hl_range / 12
        
        l1 = close - 1.1 * hl_range / 12
        l2 = close - 1.1 * hl_range / 6
        l3 = close - 1.1 * hl_range / 4
        l4 = close - 1.1 * hl_range / 2
        
        return {
            'h4': h4,
            'h3': h3,
            'h2': h2,
            'h1': h1,
            'l1': l1,
            'l2': l2,
            'l3': l3,
            'l4': l4,
        }
    
    @staticmethod
    def calculate_woodie_pivot(high: float, low: float, close: float) -> Dict[str, float]:
        """
        Woodie Pivot Points
        Emphasizes closing price
        
        Pivot = (H + L + 2*C) / 4
        """
        pivot = (high + low + 2 * close) / 4
        
        r1 = (2 * pivot) - low
        r2 = pivot + (high - low)
        
        s1 = (2 * pivot) - high
        s2 = pivot - (high - low)
        
        return {
            'pivot': pivot,
            'r1': r1,
            'r2': r2,
            's1': s1,
            's2': s2,
        }
    
    @staticmethod
    def find_nearest_pivot_level(
        price: float,
        pivot_data: Dict[str, float],
        tolerance: float = 0.001  # 0.1% default
    ) -> Dict:
        """
        Find nearest pivot level to current price
        
        Returns:
        - level: The nearest pivot level (R1, R2, S1, S2, etc.)
        - distance: Distance in percentage
        - type: 'resistance' or 'support'
        """
        levels = []
        
        for level_name, level_price in pivot_data.items():
            distance = abs(price - level_price) / price
            direction = 'resistance' if level_price > price else 'support'
            levels.append({
                'name': level_name,
                'price': level_price,
                'distance': distance,
                'direction': direction,
            })
        
        # Sort by distance
        levels.sort(key=lambda x: x['distance'])
        
        nearest = levels[0]
        
        # Check if price is within tolerance
        if nearest['distance'] <= tolerance:
            return {
                'is_at_level': True,
                'level': nearest['name'],
                'price': nearest['price'],
                'distance': nearest['distance'],
                'type': nearest['direction'],
            }
        else:
            return {
                'is_at_level': False,
                'level': None,
                'price': None,
                'distance': nearest['distance'],
                'type': None,
            }


if __name__ == "__main__":
    # Example: Daily candle
    high = 1.2150
    low = 1.2050
    close = 1.2100
    
    pivots = PivotPoints.calculate_floor_pivot(high, low, close)
    
    print("Floor Pivot Points:")
    for level, price in pivots.items():
        print(f"  {level}: {price:.4f}")
    
    # Find nearest level
    current_price = 1.2105
    nearest = PivotPoints.find_nearest_pivot_level(current_price, pivots)
    print(f"\nCurrent Price: {current_price}")
    print(f"Nearest Level: {nearest['level']} at {nearest['price']:.4f}")
