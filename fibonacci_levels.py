"""
Fibonacci Retracement Levels for Trading
Implements the Baby Pips Fibonacci retracement methodology
Used to identify potential support/resistance levels
"""
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class FibonacciLevel:
    """Represents a single Fibonacci level"""
    ratio: float            # 0.236, 0.382, 0.618, etc.
    level_type: str        # 'retracement' or 'extension'
    level: float           # Actual price level
    percentage: float      # Percentage of move (23.6%, 38.2%, etc.)
    description: str       # Human-readable description


class FibonacciLevels:
    """
    Calculate Fibonacci retracement and extension levels
    
    Fibonacci retracements identify support/resistance during pullbacks
    Fibonacci extensions identify potential target levels beyond recent highs/lows
    
    The Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144...
    
    Key Ratios (derived from Fibonacci sequence):
    - 23.6% (0.236)
    - 38.2% (0.382)
    - 50.0% (0.500)
    - 61.8% (0.618) - The Golden Ratio / Golden Mean
    - 78.6% (0.786)
    
    Extensions (beyond 100%):
    - 161.8% (1.618)
    - 261.8% (2.618)
    - 423.6% (4.236)
    """
    
    # Standard Fibonacci retracement levels
    RETRACEMENT_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786]
    
    # Fibonacci extension levels (beyond 100%)
    EXTENSION_LEVELS = [1.618, 2.618, 4.236]
    
    # All levels combined
    ALL_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.0, 1.618, 2.618, 4.236]
    
    @staticmethod
    def calculate_retracements(
        swing_high: float,
        swing_low: float,
        include_extensions: bool = False
    ) -> Dict[str, FibonacciLevel]:
        """
        Calculate Fibonacci retracement levels
        
        Args:
            swing_high: The highest price in the move (peak)
            swing_low: The lowest price in the move (trough)
            include_extensions: Include extension levels beyond the swing
        
        Returns:
            Dictionary of Fibonacci levels with metadata
        
        Formula:
            Retracement Level = Swing High - (Swing High - Swing Low) × Ratio
        """
        if swing_high <= swing_low:
            raise ValueError("Swing high must be greater than swing low")
        
        move_distance = swing_high - swing_low
        levels = {}
        
        # Calculate retracement levels
        for ratio in FibonacciLevels.RETRACEMENT_LEVELS:
            level = swing_high - (move_distance * ratio)
            percentage = ratio * 100
            
            levels[f"{percentage:.1f}%"] = FibonacciLevel(
                ratio=ratio,
                level_type="retracement",
                level=level,
                percentage=percentage,
                description=f"Fibonacci {percentage:.1f}% Retracement"
            )
        
        # Add 100% level (the original low)
        levels["100.0%"] = FibonacciLevel(
            ratio=1.0,
            level_type="origin",
            level=swing_low,
            percentage=100.0,
            description="Original Swing Low (100%)"
        )
        
        # Calculate extension levels if requested
        if include_extensions:
            for ratio in FibonacciLevels.EXTENSION_LEVELS:
                level = swing_high + (move_distance * (ratio - 1.0))
                percentage = ratio * 100
                
                levels[f"{percentage:.1f}%"] = FibonacciLevel(
                    ratio=ratio,
                    level_type="extension",
                    level=level,
                    percentage=percentage,
                    description=f"Fibonacci {percentage:.1f}% Extension"
                )
        
        return levels
    
    @staticmethod
    def calculate_extensions(
        swing_high: float,
        swing_low: float,
        breakout_high: Optional[float] = None
    ) -> Dict[str, FibonacciLevel]:
        """
        Calculate Fibonacci extension levels
        Used to find potential profit targets when price breaks above the swing high
        
        Args:
            swing_high: The highest price in the previous move
            swing_low: The lowest price in the previous move
            breakout_high: Optional new high (for reference)
        
        Returns:
            Dictionary of extension levels
        
        Formula:
            Extension Level = Swing High + (Swing High - Swing Low) × (Ratio - 1.0)
        """
        if swing_high <= swing_low:
            raise ValueError("Swing high must be greater than swing low")
        
        move_distance = swing_high - swing_low
        levels = {}
        
        # Add previous swing high as reference
        levels["0.0%"] = FibonacciLevel(
            ratio=1.0,
            level_type="reference",
            level=swing_high,
            percentage=0.0,
            description="Previous Swing High (Reference)"
        )
        
        # Calculate extension levels
        for ratio in FibonacciLevels.EXTENSION_LEVELS:
            level = swing_high + (move_distance * (ratio - 1.0))
            percentage = (ratio - 1.0) * 100
            
            levels[f"{percentage:.1f}%"] = FibonacciLevel(
                ratio=ratio,
                level_type="extension",
                level=level,
                percentage=percentage,
                description=f"Fibonacci {percentage:.1f}% Extension Target"
            )
        
        return levels
    
    @staticmethod
    def find_nearest_fibonacci_level(
        price: float,
        levels_dict: Dict[str, FibonacciLevel],
        tolerance: float = 0.003  # 0.3% tolerance
    ) -> Tuple[Optional[str], Optional[FibonacciLevel], float]:
        """
        Find nearest Fibonacci level to current price
        
        Args:
            price: Current price
            levels_dict: Dictionary of Fibonacci levels (from calculate_retracements)
            tolerance: Proximity tolerance (default 0.3%)
        
        Returns:
            Tuple of (level_name, level_data, distance_percent)
        """
        if not levels_dict:
            return None, None, float('inf')
        
        nearest_name = None
        nearest_level = None
        min_distance = float('inf')
        
        for level_name, level_data in levels_dict.items():
            # Calculate distance as percentage
            distance_percent = abs(price - level_data.level) / price
            
            if distance_percent < min_distance:
                min_distance = distance_percent
                nearest_name = level_name
                nearest_level = level_data
        
        # Check if within tolerance
        if min_distance <= tolerance:
            return nearest_name, nearest_level, min_distance
        else:
            return None, None, min_distance
    
    @staticmethod
    def get_support_resistance_levels(
        swing_high: float,
        swing_low: float
    ) -> Dict[str, Dict]:
        """
        Get combined Fibonacci levels for support and resistance analysis
        
        Returns levels organized by strength
        Stronger levels: 38.2%, 50%, 61.8%
        Weaker levels: 23.6%, 78.6%
        """
        retracements = FibonacciLevels.calculate_retracements(swing_high, swing_low)
        
        return {
            'strong_levels': {
                '38.2%': retracements.get('38.2%'),
                '50.0%': retracements.get('50.0%'),
                '61.8%': retracements.get('61.8%'),
            },
            'weak_levels': {
                '23.6%': retracements.get('23.6%'),
                '78.6%': retracements.get('78.6%'),
            },
            'origin': {
                '100.0%': retracements.get('100.0%'),
            },
            'all_levels': retracements
        }
    
    @staticmethod
    def analyze_price_action_at_fibonacci(
        price: float,
        levels_dict: Dict[str, FibonacciLevel],
        tolerance: float = 0.003
    ) -> Dict:
        """
        Analyze if price is at a Fibonacci level
        Returns confidence score based on proximity
        
        Args:
            price: Current price
            levels_dict: Fibonacci levels dictionary
            tolerance: Proximity tolerance
        
        Returns:
            Dictionary with:
            - at_level: bool - Is price at a Fibonacci level?
            - nearest_level: str - Name of nearest level
            - distance: float - Distance to nearest level (%)
            - level_price: float - Price of nearest level
            - confidence: float - 0-1 confidence based on proximity
            - level_type: str - Type of level (retracement/extension)
        """
        level_name, level_data, distance = FibonacciLevels.find_nearest_fibonacci_level(
            price, levels_dict, tolerance * 2  # Check wider tolerance first
        )
        
        if level_data is None:
            return {
                'at_level': False,
                'nearest_level': None,
                'distance': distance,
                'level_price': None,
                'confidence': 0.0,
                'level_type': None
            }
        
        # Calculate confidence based on distance
        # Perfect match (distance=0) = 1.0 confidence
        # At tolerance boundary = 0.5 confidence
        confidence = max(0.0, 1.0 - (distance / tolerance))
        
        return {
            'at_level': distance <= tolerance,
            'nearest_level': level_name,
            'distance': distance,
            'level_price': level_data.level,
            'confidence': confidence,
            'level_type': level_data.level_type,
            'description': level_data.description
        }
    
    @staticmethod
    def identify_fibonacci_bounce(
        price: float,
        previous_close: float,
        swing_high: float,
        swing_low: float,
        tolerance: float = 0.003
    ) -> Dict:
        """
        Identify if price is bouncing from a Fibonacci level
        
        Bounce indicators:
        - Price near Fibonacci level (within tolerance)
        - Previous close was below level, current price above
        - Strong momentum away from level
        
        Args:
            price: Current price
            previous_close: Previous candle close
            swing_high: Recent swing high
            swing_low: Recent swing low
            tolerance: Proximity tolerance
        
        Returns:
            Dictionary with bounce analysis
        """
        levels = FibonacciLevels.calculate_retracements(swing_high, swing_low)
        analysis = FibonacciLevels.analyze_price_action_at_fibonacci(
            price, levels, tolerance
        )
        
        if not analysis['at_level']:
            return {
                'bouncing': False,
                'nearest_level': None,
                'bounce_strength': 0.0,
                'direction': None
            }
        
        # Check bounce direction
        level_price = analysis['level_price']
        
        # Upward bounce (price below level, now above)
        if previous_close < level_price <= price:
            bounce_strength = min(1.0, (price - level_price) / (swing_high - swing_low))
            return {
                'bouncing': bounce_strength > 0.1,
                'nearest_level': analysis['nearest_level'],
                'bounce_strength': bounce_strength,
                'direction': 'up',
                'description': f"Bouncing UP from {analysis['nearest_level']} Fibonacci level"
            }
        
        # Downward bounce (price above level, now below)
        elif level_price >= price > previous_close:
            bounce_strength = min(1.0, (level_price - price) / (swing_high - swing_low))
            return {
                'bouncing': bounce_strength > 0.1,
                'nearest_level': analysis['nearest_level'],
                'bounce_strength': bounce_strength,
                'direction': 'down',
                'description': f"Bouncing DOWN from {analysis['nearest_level']} Fibonacci level"
            }
        
        else:
            return {
                'bouncing': False,
                'nearest_level': analysis['nearest_level'],
                'bounce_strength': 0.0,
                'direction': None
            }
    
    @staticmethod
    def identify_fibonacci_breakout(
        price: float,
        previous_high: float,
        swing_high: float,
        swing_low: float,
        breakout_threshold: float = 0.005  # 0.5% above level
    ) -> Dict:
        """
        Identify if price is breaking out above/below Fibonacci level
        
        Breakout indicators:
        - Price clearly above/below Fibonacci level
        - Previous close was on opposite side of level
        - Strong move away from level
        
        Args:
            price: Current price
            previous_high: Previous candle high
            swing_high: Recent swing high
            swing_low: Recent swing low
            breakout_threshold: How far above/below to confirm breakout
        
        Returns:
            Dictionary with breakout analysis
        """
        levels = FibonacciLevels.calculate_retracements(swing_high, swing_low)
        analysis = FibonacciLevels.analyze_price_action_at_fibonacci(
            price, levels, 0.01  # Check wider range for breakout
        )
        
        if analysis['nearest_level'] is None:
            return {
                'breaking_out': False,
                'level': None,
                'breakout_strength': 0.0,
                'direction': None
            }
        
        level_price = analysis['level_price']
        move_distance = swing_high - swing_low
        
        # Check upward breakout
        if price > level_price + (move_distance * breakout_threshold):
            if previous_high <= level_price:
                breakout_strength = min(1.0, (price - level_price) / move_distance)
                return {
                    'breaking_out': True,
                    'level': analysis['nearest_level'],
                    'level_price': level_price,
                    'breakout_strength': breakout_strength,
                    'direction': 'up',
                    'distance_above': price - level_price,
                    'description': f"BREAKING OUT ABOVE {analysis['nearest_level']} Fibonacci level"
                }
        
        # Check downward breakout
        elif price < level_price - (move_distance * breakout_threshold):
            if previous_high >= level_price:
                breakout_strength = min(1.0, (level_price - price) / move_distance)
                return {
                    'breaking_out': True,
                    'level': analysis['nearest_level'],
                    'level_price': level_price,
                    'breakout_strength': breakout_strength,
                    'direction': 'down',
                    'distance_below': level_price - price,
                    'description': f"BREAKING OUT BELOW {analysis['nearest_level']} Fibonacci level"
                }
        
        return {
            'breaking_out': False,
            'level': None,
            'breakout_strength': 0.0,
            'direction': None
        }


# Usage Examples
if __name__ == "__main__":
    # Example 1: Calculate retracement levels
    print("=" * 70)
    print("FIBONACCI RETRACEMENT LEVELS")
    print("=" * 70)
    
    swing_high = 65000
    swing_low = 60000
    current_price = 62500
    
    retracements = FibonacciLevels.calculate_retracements(swing_high, swing_low)
    
    print(f"\nMove: {swing_high} (high) to {swing_low} (low)")
    print(f"Current Price: {current_price}\n")
    
    for level_name, level_data in sorted(retracements.items()):
        print(f"  {level_name:6} ({level_data.description}): {level_data.level:,.2f}")
    
    # Find nearest level
    nearest_name, nearest_level, distance = FibonacciLevels.find_nearest_fibonacci_level(
        current_price, retracements
    )
    print(f"\nNearest Level: {nearest_name} at {nearest_level.level:,.2f}")
    print(f"Distance: {distance:.2%}")
    
    # Example 2: Extension levels
    print("\n" + "=" * 70)
    print("FIBONACCI EXTENSION LEVELS")
    print("=" * 70)
    
    extensions = FibonacciLevels.calculate_extensions(swing_high, swing_low)
    
    print(f"\nTargets if price breaks above {swing_high}:\n")
    for level_name, level_data in sorted(extensions.items()):
        print(f"  {level_name:6} ({level_data.description}): {level_data.level:,.2f}")
    
    # Example 3: Bounce detection
    print("\n" + "=" * 70)
    print("BOUNCE DETECTION")
    print("=" * 70)
    
    bounce = FibonacciLevels.identify_fibonacci_bounce(
        price=62100,
        previous_close=61800,
        swing_high=swing_high,
        swing_low=swing_low
    )
    
    print(f"\n{bounce}")
