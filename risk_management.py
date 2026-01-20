"""
Risk Management & TP/SL Placement Engine
Determines optimal take profit and stop loss levels for each trade
Based on support/resistance levels, Fibonacci extensions, and risk/reward ratios
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List
from enum import Enum


class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class RiskManagementConfig:
    """Configuration for risk management"""
    
    # TP/SL Calculation Method
    use_fibonacci_for_tp: bool = True      # Use Fibonacci extensions for TP targets
    use_pivot_for_tp: bool = True          # Use pivot R1, R2, R3 for TP targets
    
    # Risk/Reward Ratios for TP levels
    tp1_risk_reward: float = 1.0           # TP1: 1:1 ratio (reach first target, equal to risk)
    tp2_risk_reward: float = 2.0           # TP2: 2:1 ratio (go further)
    tp3_risk_reward: float = 3.0           # TP3: 3:1 ratio (max profit target)
    
    # Position Sizing for TP levels (what % of position to close)
    tp1_size: float = 0.33                 # Close 33% at TP1
    tp2_size: float = 0.33                 # Close 33% at TP2
    tp3_size: float = 0.34                 # Close 34% at TP3 (let winners run)
    
    # Stop Loss Parameters
    use_support_offset_for_sl: bool = True # SL below support by offset
    sl_support_offset: float = 0.005       # SL = Support - 0.5% for long trades
    sl_resistance_offset: float = 0.005    # SL = Resistance + 0.5% for short trades
    
    # Maximum Risk Per Trade
    max_risk_percent: float = 2.0          # Max 2% account risk per trade
    
    # ATR-based SL (volatility adjustment)
    use_atr_for_sl: bool = True            # Use ATR to adjust SL based on volatility
    atr_multiplier: float = 1.5            # SL = Entry ± (ATR × 1.5)


class RiskManagement:
    """Calculate stop loss and take profit levels for trades"""
    
    def __init__(self, config: RiskManagementConfig = None):
        self.config = config or RiskManagementConfig()
    
    def calculate_long_trade_levels(
        self,
        entry_price: float,
        support_level: float,
        pivot_data: Dict[str, float] = None,
        fibonacci_data: Dict[str, float] = None,
        atr: float = None,
        highest_recent_price: float = None,
    ) -> Dict:
        """
        Calculate LONG trade levels (SL below support, TPs above entry)
        
        Parameters:
        - entry_price: Entry price (at support level)
        - support_level: Support level where price is buying
        - pivot_data: Pivot levels (R1, R2, R3, etc.)
        - fibonacci_data: Fibonacci extension levels
        - atr: Average True Range for volatility adjustment
        - highest_recent_price: Highest price in recent period
        
        Returns:
        {
            'entry': float,
            'stop_loss': float,
            'sl_reason': str,
            'risk': float,
            'tp1': {'price': float, 'risk_reward': float, 'position_size': float},
            'tp2': {'price': float, 'risk_reward': float, 'position_size': float},
            'tp3': {'price': float, 'risk_reward': float, 'position_size': float},
            'risk_reward_ratio': float,
            'trade_description': str,
        }
        """
        # Calculate Stop Loss
        stop_loss = self._calculate_long_stop_loss(support_level, atr)
        risk = entry_price - stop_loss
        
        if risk <= 0:
            return {
                'error': 'Invalid risk calculation - support level too close',
                'entry': entry_price,
                'stop_loss': stop_loss,
            }
        
        # Collect TP targets from multiple sources
        tp_candidates = self._gather_long_tp_candidates(
            entry_price,
            pivot_data,
            fibonacci_data,
            highest_recent_price
        )
        
        # Sort candidates by price (ascending - closest first)
        tp_candidates.sort(key=lambda x: x['price'])
        
        # Assign TP levels using risk/reward ratios
        tp1 = self._assign_tp_level(
            entry_price,
            risk,
            tp_candidates,
            self.config.tp1_risk_reward,
            self.config.tp1_size,
            min_distance=0.001  # Minimum 0.1% above entry
        )
        
        tp2 = self._assign_tp_level(
            entry_price,
            risk,
            tp_candidates,
            self.config.tp2_risk_reward,
            self.config.tp2_size,
            min_distance=tp1['price'] if tp1 else 0.001
        )
        
        tp3 = self._assign_tp_level(
            entry_price,
            risk,
            tp_candidates,
            self.config.tp3_risk_reward,
            self.config.tp3_size,
            min_distance=tp2['price'] if tp2 else 0.001
        )
        
        # Risk/Reward ratio for the full trade
        if tp3:
            overall_rr = (tp3['price'] - entry_price) / risk
        elif tp2:
            overall_rr = (tp2['price'] - entry_price) / risk
        elif tp1:
            overall_rr = (tp1['price'] - entry_price) / risk
        else:
            overall_rr = 0
        
        # Build trade description with None handling
        tp1_str = f"{tp1['price']:.2f}" if tp1 else "N/A"
        tp2_str = f"{tp2['price']:.2f}" if tp2 else "N/A"
        tp3_str = f"{tp3['price']:.2f}" if tp3 else "N/A"
        
        return {
            'direction': 'LONG',
            'entry': entry_price,
            'support_level': support_level,
            'stop_loss': stop_loss,
            'sl_reason': f'Below support ({support_level:.2f}) with {self.config.sl_support_offset*100:.2f}% buffer',
            'risk': risk,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'risk_reward_ratio': overall_rr,
            'trade_description': (
                f"LONG: Entry {entry_price:.2f} | "
                f"SL {stop_loss:.2f} (Risk: {risk:.4f}) | "
                f"TP1 {tp1_str} | "
                f"TP2 {tp2_str} | "
                f"TP3 {tp3_str} | "
                f"RR: {overall_rr:.2f}:1"
            ),
        }
    
    def calculate_short_trade_levels(
        self,
        entry_price: float,
        resistance_level: float,
        pivot_data: Dict[str, float] = None,
        fibonacci_data: Dict[str, float] = None,
        atr: float = None,
        lowest_recent_price: float = None,
    ) -> Dict:
        """
        Calculate SHORT trade levels (SL above resistance, TPs below entry)
        
        Parameters:
        - entry_price: Entry price (at resistance level)
        - resistance_level: Resistance level where price is selling
        - pivot_data: Pivot levels (S1, S2, S3, etc.)
        - fibonacci_data: Fibonacci retracement levels
        - atr: Average True Range for volatility adjustment
        - lowest_recent_price: Lowest price in recent period
        
        Returns: Similar structure to LONG but with prices inverted
        """
        # Calculate Stop Loss
        stop_loss = self._calculate_short_stop_loss(resistance_level, atr)
        risk = stop_loss - entry_price
        
        if risk <= 0:
            return {
                'error': 'Invalid risk calculation - resistance level too close',
                'entry': entry_price,
                'stop_loss': stop_loss,
            }
        
        # Collect TP targets from multiple sources
        tp_candidates = self._gather_short_tp_candidates(
            entry_price,
            pivot_data,
            fibonacci_data,
            lowest_recent_price
        )
        
        # Sort candidates by price (descending - closest first)
        tp_candidates.sort(key=lambda x: x['price'], reverse=True)
        
        # Assign TP levels using risk/reward ratios
        tp1 = self._assign_tp_level_short(
            entry_price,
            risk,
            tp_candidates,
            self.config.tp1_risk_reward,
            self.config.tp1_size,
            max_distance=0.001  # Minimum 0.1% below entry
        )
        
        tp2 = self._assign_tp_level_short(
            entry_price,
            risk,
            tp_candidates,
            self.config.tp2_risk_reward,
            self.config.tp2_size,
            max_distance=tp1['price'] if tp1 else 0.001
        )
        
        tp3 = self._assign_tp_level_short(
            entry_price,
            risk,
            tp_candidates,
            self.config.tp3_risk_reward,
            self.config.tp3_size,
            max_distance=tp2['price'] if tp2 else 0.001
        )
        
        # Risk/Reward ratio for the full trade
        if tp3:
            overall_rr = (entry_price - tp3['price']) / risk
        elif tp2:
            overall_rr = (entry_price - tp2['price']) / risk
        elif tp1:
            overall_rr = (entry_price - tp1['price']) / risk
        else:
            overall_rr = 0
        
        # Build trade description with None handling
        tp1_str = f"{tp1['price']:.2f}" if tp1 else "N/A"
        tp2_str = f"{tp2['price']:.2f}" if tp2 else "N/A"
        tp3_str = f"{tp3['price']:.2f}" if tp3 else "N/A"
        
        return {
            'direction': 'SHORT',
            'entry': entry_price,
            'resistance_level': resistance_level,
            'stop_loss': stop_loss,
            'sl_reason': f'Above resistance ({resistance_level:.2f}) with {self.config.sl_resistance_offset*100:.2f}% buffer',
            'risk': risk,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'risk_reward_ratio': overall_rr,
            'trade_description': (
                f"SHORT: Entry {entry_price:.2f} | "
                f"SL {stop_loss:.2f} (Risk: {risk:.4f}) | "
                f"TP1 {tp1_str} | "
                f"TP2 {tp2_str} | "
                f"TP3 {tp3_str} | "
                f"RR: {overall_rr:.2f}:1"
            ),
        }
    
    # ========== STOP LOSS CALCULATION ==========
    
    def _calculate_long_stop_loss(
        self,
        support_level: float,
        atr: Optional[float] = None
    ) -> float:
        """
        Calculate stop loss for LONG trades
        
        For LONG: SL = Support - offset
        If using ATR: SL = Support - (ATR × multiplier)
        Take the tighter (higher) of the two
        """
        # Base SL: Support minus offset
        base_sl = support_level * (1 - self.config.sl_support_offset)
        
        # If ATR available, use it as alternative
        if self.config.use_atr_for_sl and atr:
            atr_sl = support_level - (atr * self.config.atr_multiplier)
            # Use tighter SL (higher price = tighter risk)
            return max(base_sl, atr_sl)
        
        return base_sl
    
    def _calculate_short_stop_loss(
        self,
        resistance_level: float,
        atr: Optional[float] = None
    ) -> float:
        """
        Calculate stop loss for SHORT trades
        
        For SHORT: SL = Resistance + offset
        If using ATR: SL = Resistance + (ATR × multiplier)
        Take the tighter (lower) of the two
        """
        # Base SL: Resistance plus offset
        base_sl = resistance_level * (1 + self.config.sl_resistance_offset)
        
        # If ATR available, use it as alternative
        if self.config.use_atr_for_sl and atr:
            atr_sl = resistance_level + (atr * self.config.atr_multiplier)
            # Use tighter SL (lower price = tighter risk)
            return min(base_sl, atr_sl)
        
        return base_sl
    
    # ========== TAKE PROFIT CANDIDATE GATHERING ==========
    
    def _gather_long_tp_candidates(
        self,
        entry_price: float,
        pivot_data: Optional[Dict[str, float]] = None,
        fibonacci_data: Optional[Dict[str, float]] = None,
        highest_recent: Optional[float] = None,
    ) -> List[Dict]:
        """
        Gather all potential TP targets above entry price
        
        Sources:
        1. Pivot R1, R2, R3
        2. Fibonacci extension levels (161.8%, 261.8%, 423.6%)
        3. Recent swing high
        """
        candidates = []
        
        # Add Pivot targets (resistance levels above entry)
        if self.config.use_pivot_for_tp and pivot_data:
            for level_name in ['r1', 'r2', 'r3']:
                if level_name in pivot_data:
                    price = pivot_data[level_name]
                    if price > entry_price:
                        candidates.append({
                            'price': price,
                            'source': f'Pivot {level_name.upper()}',
                            'strength': 0.7 if level_name == 'r1' else 0.8 if level_name == 'r2' else 0.9,
                        })
        
        # Add Fibonacci extension targets
        if self.config.use_fibonacci_for_tp and fibonacci_data:
            # Extension levels: 161.8%, 261.8%, 423.6%
            for ext_ratio in ['1.618', '2.618', '4.236']:
                if ext_ratio in fibonacci_data:
                    price = fibonacci_data[ext_ratio]
                    if price > entry_price:
                        candidates.append({
                            'price': price,
                            'source': f'Fibonacci {ext_ratio}',
                            'strength': 0.75 if ext_ratio == '1.618' else 0.85 if ext_ratio == '2.618' else 0.95,
                        })
        
        # Add recent swing high
        if highest_recent and highest_recent > entry_price:
            candidates.append({
                'price': highest_recent,
                'source': 'Recent Swing High',
                'strength': 0.65,
            })
        
        return candidates if candidates else [{
            'price': entry_price * 1.05,  # Default: 5% above entry
            'source': 'Default (5% above entry)',
            'strength': 0.5,
        }]
    
    def _gather_short_tp_candidates(
        self,
        entry_price: float,
        pivot_data: Optional[Dict[str, float]] = None,
        fibonacci_data: Optional[Dict[str, float]] = None,
        lowest_recent: Optional[float] = None,
    ) -> List[Dict]:
        """
        Gather all potential TP targets below entry price (for SHORT trades)
        
        Sources:
        1. Pivot S1, S2, S3
        2. Fibonacci retracement levels (38.2%, 50%, 61.8%)
        3. Recent swing low
        """
        candidates = []
        
        # Add Pivot targets (support levels below entry)
        if self.config.use_pivot_for_tp and pivot_data:
            for level_name in ['s1', 's2', 's3']:
                if level_name in pivot_data:
                    price = pivot_data[level_name]
                    if price < entry_price:
                        candidates.append({
                            'price': price,
                            'source': f'Pivot {level_name.upper()}',
                            'strength': 0.7 if level_name == 's1' else 0.8 if level_name == 's2' else 0.9,
                        })
        
        # Add Fibonacci retracement targets (price drops to Fib level)
        if self.config.use_fibonacci_for_tp and fibonacci_data:
            # Retracement levels: 38.2%, 50%, 61.8%, 78.6%
            for ratio in ['0.382', '0.5', '0.618', '0.786']:
                if ratio in fibonacci_data:
                    price = fibonacci_data[ratio]
                    if price < entry_price:
                        candidates.append({
                            'price': price,
                            'source': f'Fibonacci {float(ratio)*100:.1f}%',
                            'strength': 0.75 if ratio == '0.618' else 0.7 if ratio == '0.5' else 0.65,
                        })
        
        # Add recent swing low
        if lowest_recent and lowest_recent < entry_price:
            candidates.append({
                'price': lowest_recent,
                'source': 'Recent Swing Low',
                'strength': 0.65,
            })
        
        return candidates if candidates else [{
            'price': entry_price * 0.95,  # Default: 5% below entry
            'source': 'Default (5% below entry)',
            'strength': 0.5,
        }]
    
    # ========== TP LEVEL ASSIGNMENT ==========
    
    def _assign_tp_level(
        self,
        entry_price: float,
        risk: float,
        candidates: List[Dict],
        risk_reward_ratio: float,
        position_size: float,
        min_distance: float = 0.0,
    ) -> Optional[Dict]:
        """
        Find TP level that matches risk/reward ratio for LONG trades
        
        Logic:
        - Calculate target price: Entry + (Risk × Risk/Reward Ratio)
        - Find nearest candidate above or at this price
        - Use that as TP level
        """
        if not candidates:
            return None
        
        # Calculate ideal TP price based on risk/reward
        ideal_tp = entry_price + (risk * risk_reward_ratio)
        
        # Find best candidate (closest to ideal, but not below it)
        best_candidate = None
        best_distance = float('inf')
        
        for candidate in candidates:
            if candidate['price'] >= min_distance:  # Must be above minimum
                distance = abs(candidate['price'] - ideal_tp)
                if distance < best_distance:
                    best_distance = distance
                    best_candidate = candidate
        
        if not best_candidate:
            return None
        
        return {
            'price': best_candidate['price'],
            'source': best_candidate['source'],
            'risk_reward': (best_candidate['price'] - entry_price) / risk if risk > 0 else 0,
            'position_size': position_size,
            'profit': best_candidate['price'] - entry_price,
        }
    
    def _assign_tp_level_short(
        self,
        entry_price: float,
        risk: float,
        candidates: List[Dict],
        risk_reward_ratio: float,
        position_size: float,
        max_distance: float = float('inf'),
    ) -> Optional[Dict]:
        """
        Find TP level that matches risk/reward ratio for SHORT trades
        
        Logic:
        - Calculate target price: Entry - (Risk × Risk/Reward Ratio)
        - Find nearest candidate below or at this price
        - Use that as TP level
        """
        if not candidates:
            return None
        
        # Calculate ideal TP price based on risk/reward
        ideal_tp = entry_price - (risk * risk_reward_ratio)
        
        # Find best candidate (closest to ideal, but not above it)
        best_candidate = None
        best_distance = float('inf')
        
        for candidate in candidates:
            if candidate['price'] <= max_distance:  # Must be below maximum
                distance = abs(candidate['price'] - ideal_tp)
                if distance < best_distance:
                    best_distance = distance
                    best_candidate = candidate
        
        if not best_candidate:
            return None
        
        return {
            'price': best_candidate['price'],
            'source': best_candidate['source'],
            'risk_reward': (entry_price - best_candidate['price']) / risk if risk > 0 else 0,
            'position_size': position_size,
            'profit': entry_price - best_candidate['price'],
        }
    
    # ========== UTILITY METHODS ==========
    
    def adjust_tp_for_volatility(
        self,
        base_tp: float,
        atr: float,
        volatility_level: str = "normal",
        direction: str = "long",
    ) -> float:
        """
        Adjust TP based on market volatility
        
        - Low volatility (calm market): Tighter TPs (closer to entry)
        - High volatility (choppy market): Wider TPs (further from entry)
        """
        if volatility_level == "high":
            # Move TP further away (5-10% more)
            adjustment = 1.07 if direction == "long" else 0.93
        elif volatility_level == "low":
            # Move TP closer (5-10% less)
            adjustment = 1.03 if direction == "long" else 0.97
        else:
            # Normal: no adjustment
            adjustment = 1.0
        
        return base_tp * adjustment
    
    def validate_trade_setup(self, trade_levels: Dict) -> Dict:
        """
        Validate trade setup before execution
        
        Checks:
        - Risk/Reward ratio >= 1.5:1
        - Risk <= max_risk_percent
        - TP above/below entry for direction
        - SL properly placed
        """
        validation = {
            'is_valid': True,
            'warnings': [],
            'errors': [],
        }
        
        if 'error' in trade_levels:
            validation['is_valid'] = False
            validation['errors'].append(trade_levels['error'])
            return validation
        
        rr = trade_levels.get('risk_reward_ratio', 0)
        
        # Check 1: Risk/Reward ratio
        if rr < 1.0:
            validation['errors'].append(f'Risk/Reward too low: {rr:.2f}:1 (need >= 1.0:1)')
            validation['is_valid'] = False
        elif rr < 1.5:
            validation['warnings'].append(f'Risk/Reward slightly low: {rr:.2f}:1 (ideal >= 1.5:1)')
        
        # Check 2: SL properly placed
        direction = trade_levels.get('direction')
        entry = trade_levels.get('entry', 0)
        sl = trade_levels.get('stop_loss', 0)
        
        if direction == 'LONG' and sl >= entry:
            validation['errors'].append(f'SL {sl:.2f} not below entry {entry:.2f}')
            validation['is_valid'] = False
        elif direction == 'SHORT' and sl <= entry:
            validation['errors'].append(f'SL {sl:.2f} not above entry {entry:.2f}')
            validation['is_valid'] = False
        
        # Check 3: TP levels exist and are properly ordered
        tp1 = trade_levels.get('tp1')
        tp2 = trade_levels.get('tp2')
        tp3 = trade_levels.get('tp3')
        
        if not tp1:
            validation['warnings'].append('No TP1 calculated')
        
        if direction == 'LONG':
            if tp1 and tp1['price'] <= entry:
                validation['errors'].append('TP1 not above entry')
                validation['is_valid'] = False
            if tp2 and tp1 and tp2['price'] <= tp1['price']:
                validation['errors'].append('TP2 not above TP1')
                validation['is_valid'] = False
            if tp3 and tp2 and tp3['price'] <= tp2['price']:
                validation['errors'].append('TP3 not above TP2')
                validation['is_valid'] = False
        else:  # SHORT
            if tp1 and tp1['price'] >= entry:
                validation['errors'].append('TP1 not below entry')
                validation['is_valid'] = False
            if tp2 and tp1 and tp2['price'] >= tp1['price']:
                validation['errors'].append('TP2 not below TP1')
                validation['is_valid'] = False
            if tp3 and tp2 and tp3['price'] >= tp2['price']:
                validation['errors'].append('TP3 not below TP2')
                validation['is_valid'] = False
        
        return validation


# Example usage
if __name__ == "__main__":
    # Example LONG trade
    rm = RiskManagement()
    
    pivot_example = {
        'pivot': 62200,
        'r1': 62500,
        'r2': 62800,
        'r3': 63100,
        's1': 61900,
        's2': 61600,
        's3': 61300,
    }
    
    fib_example = {
        '0.236': 61850,
        '0.382': 61700,
        '0.5': 61550,
        '0.618': 61400,
        '1.618': 63100,
        '2.618': 64300,
    }
    
    long_levels = rm.calculate_long_trade_levels(
        entry_price=62000,
        support_level=61900,
        pivot_data=pivot_example,
        fibonacci_data=fib_example,
        atr=150,
        highest_recent_price=63500,
    )
    
    print("=" * 60)
    print("LONG TRADE SETUP")
    print("=" * 60)
    print(f"Entry: ${long_levels['entry']:.2f}")
    print(f"Stop Loss: ${long_levels['stop_loss']:.2f}")
    print(f"Risk: ${long_levels['risk']:.2f}")
    print(f"\nTake Profit Levels:")
    print(f"  TP1: ${long_levels['tp1']['price']:.2f} (RR: {long_levels['tp1']['risk_reward']:.2f}:1) - {long_levels['tp1']['source']}")
    print(f"  TP2: ${long_levels['tp2']['price']:.2f} (RR: {long_levels['tp2']['risk_reward']:.2f}:1) - {long_levels['tp2']['source']}")
    print(f"  TP3: ${long_levels['tp3']['price']:.2f} (RR: {long_levels['tp3']['risk_reward']:.2f}:1) - {long_levels['tp3']['source']}")
    print(f"\nOverall Risk/Reward: {long_levels['risk_reward_ratio']:.2f}:1")
    print(f"\n{long_levels['trade_description']}")
    
    # Validate setup
    validation = rm.validate_trade_setup(long_levels)
    print(f"\nValidation: {'✓ VALID' if validation['is_valid'] else '✗ INVALID'}")
    if validation['warnings']:
        print(f"Warnings: {', '.join(validation['warnings'])}")
    if validation['errors']:
        print(f"Errors: {', '.join(validation['errors'])}")
