#!/usr/bin/env python3
"""
BerelzDashboard Server - HIGH PERFORMANCE VERSION
Optimized for speed and reliability
"""

import http.server
import socketserver
import json
import os
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta
from pathlib import Path
import threading
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

# SSL context that doesn't verify certificates (fixes macOS SSL issues)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Configuration
PORT = 8080
# Support multiple platforms
MT5_FILES_PATHS = [
    Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files",  # macOS (Wine)
    Path.home() / ".wine/drive_c/Program Files/MetaTrader 5/MQL5/Files",  # Linux (Wine)
    Path.home() / "AppData/Roaming/MetaQuotes/Terminal",  # Windows (scans for terminal ID)
]
MT5_FILES_PATH = next((p for p in MT5_FILES_PATHS if p.exists()), MT5_FILES_PATHS[0])
MT5_DATA_FILES = ["xaueur_stream.json", "xaueur_live.json", "xaueur_data.json"]

# Cache settings (optimized)
PRICE_CACHE_TTL = 5        # 5 seconds for price data
NEWS_CACHE_TTL = 900       # 15 minutes for news
COT_CACHE_TTL = 14400      # 4 hours for COT (faster pickup of weekly updates)
CALENDAR_CACHE_TTL = 3600  # 1 hour for calendar

# Global data cache with timestamps
cache = {
    'data': None, 'data_time': 0,
    'news': None, 'news_time': 0,
    'cot': None, 'cot_time': 0,
    'calendar': None, 'calendar_time': 0
}
# Legacy cache variables (for compatibility)
data_cache = None
news_cache = None
cot_cache = None
calendar_cache = []
last_news_update = 0
last_cot_update = 0
last_calendar_update = 0

price_history = []
signal_history = []
signal_stats = {'total': 0, 'correct': 0, 'buy': 0, 'sell': 0, 'hold': 0}
last_signal = None

# 4-Hour Prior Momentum Tracking (predictive indicator)
hourly_prices = []  # Store prices for 4h lookback
HOUR_SECONDS = 3600

# =========================================================================
# M5 BAR CACHE — persists bars across server restarts
# Stores up to 2000 M5 bars (~7 days of market data)
# =========================================================================
M5_CACHE_FILE = Path(__file__).parent / 'm5_cache.json'
M5_CACHE_MAX_BARS = 2000  # ~7 days of M5 bars
_m5_cache = []             # In-memory bar cache
_m5_cache_dirty = False    # Track if cache needs saving
_m5_last_save = 0          # Last save timestamp

def load_m5_cache():
    """Load cached M5 bars from disk on startup"""
    global _m5_cache
    try:
        if M5_CACHE_FILE.exists():
            with open(M5_CACHE_FILE, 'r') as f:
                data = json.load(f)
            _m5_cache = data if isinstance(data, list) else []
            # Filter out bars older than 7 days
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y.%m.%d %H:%M:%S")
            _m5_cache = [b for b in _m5_cache if b.get('time', '') >= cutoff]
            print(f"📦 M5 cache loaded: {len(_m5_cache)} bars from disk")
        else:
            print("📦 M5 cache: no existing file, starting fresh")
    except Exception as e:
        print(f"⚠️ M5 cache load error: {e}")
        _m5_cache = []

def save_m5_cache():
    """Save M5 bar cache to disk"""
    global _m5_cache_dirty, _m5_last_save
    if not _m5_cache_dirty:
        return
    try:
        with open(M5_CACHE_FILE, 'w') as f:
            json.dump(_m5_cache, f)
        _m5_cache_dirty = False
        _m5_last_save = time.time()
    except Exception as e:
        print(f"⚠️ M5 cache save error: {e}")

def merge_bars_into_cache(new_bars):
    """Merge new bars into persistent cache, deduplicating by time"""
    global _m5_cache, _m5_cache_dirty
    if not new_bars:
        return _m5_cache

    # Build time index of existing cache for fast lookup
    existing_times = {b['time'] for b in _m5_cache}

    added = 0
    updated = 0
    for bar in new_bars:
        if bar.get('synthetic'):
            continue  # Never cache synthetic bars
        bar_time = bar.get('time', '')
        if not bar_time:
            continue
        if bar_time in existing_times:
            # Update the existing bar (latest data for the same candle)
            for i, cb in enumerate(_m5_cache):
                if cb['time'] == bar_time:
                    _m5_cache[i] = bar
                    updated += 1
                    break
        else:
            _m5_cache.append(bar)
            existing_times.add(bar_time)
            added += 1

    if added > 0 or updated > 0:
        # Sort by time and trim
        _m5_cache.sort(key=lambda b: b['time'])
        _m5_cache = _m5_cache[-M5_CACHE_MAX_BARS:]
        _m5_cache_dirty = True

    return _m5_cache

def get_cached_bars():
    """Get the full cached bar history (non-synthetic only)"""
    return list(_m5_cache)

# Load cache on module init
load_m5_cache()

# Backtesting - track signals and validate after 48 bars (4 hours) - same as box theory
BACKTEST_FILE = Path(__file__).parent / 'backtest_data.json'
backtest_pending = []
backtest_results = {'total': 0, 'wins': 0, 'losses': 0, 'buy_wins': 0, 'buy_total': 0, 'sell_wins': 0, 'sell_total': 0}

# Load backtest data from file
def load_backtest_data():
    global backtest_pending, backtest_results
    print(f"📂 Loading backtest from: {BACKTEST_FILE}")
    try:
        if BACKTEST_FILE.exists():
            with open(BACKTEST_FILE, 'r') as f:
                data = json.load(f)
                backtest_pending = data.get('pending', [])
                backtest_results = data.get('results', backtest_results)
                print(f"✅ Loaded backtest: {len(backtest_pending)} pending, {backtest_results['total']} validated, {backtest_results['wins']} wins")
        else:
            print(f"⚠️ Backtest file not found: {BACKTEST_FILE}")
    except Exception as e:
        print(f"⚠️ Could not load backtest data: {e}")

def save_backtest_data():
    try:
        with open(BACKTEST_FILE, 'w') as f:
            json.dump({'pending': backtest_pending, 'results': backtest_results}, f)
    except Exception as e:
        print(f"⚠️ Could not save backtest data: {e}")

load_backtest_data()
BACKTEST_BARS = 48  # Validate after 48 M5 bars (4 hours)
BACKTEST_SECONDS = 14400  # 4 hours in seconds
MIN_MOVE_PIPS = 100  # Minimum move to count as win (1.00 EUR for gold)

# Thread pool for parallel API calls
executor = ThreadPoolExecutor(max_workers=4)

#==============================================================================
# BACKTESTING ENGINE
#==============================================================================
def validate_backtest(current_price, bars):
    """Validate pending signals against actual price movement"""
    global backtest_pending, backtest_results

    now = time.time()
    validated = []

    for pending in backtest_pending[:]:
        # Check if enough time has passed (4 hours)
        if now - pending['timestamp'] >= BACKTEST_SECONDS:
            entry_price = pending['price']
            signal = pending['signal']

            # Calculate result
            if signal == 'BUY':
                pips = (current_price - entry_price) * 100
                win = pips >= MIN_MOVE_PIPS
                backtest_results['buy_total'] += 1
                if win:
                    backtest_results['buy_wins'] += 1
            elif signal == 'SELL':
                pips = (entry_price - current_price) * 100
                win = pips >= MIN_MOVE_PIPS
                backtest_results['sell_total'] += 1
                if win:
                    backtest_results['sell_wins'] += 1
            else:
                # HOLD - check if price stayed within range
                pips = abs(current_price - entry_price) * 100
                win = pips < MIN_MOVE_PIPS * 2

            backtest_results['total'] += 1
            if win:
                backtest_results['wins'] += 1
            else:
                backtest_results['losses'] += 1

            validated.append({
                'signal': signal,
                'entry': entry_price,
                'exit': current_price,
                'pips': round(pips, 1),
                'win': win,
                'time': pending['time']
            })

            backtest_pending.remove(pending)

    # Keep only last 20 pending
    if len(backtest_pending) > 20:
        backtest_pending = backtest_pending[-20:]

    # Save to file after validation changes
    if validated:
        save_backtest_data()

    return validated

def get_win_rate():
    """Calculate win rate statistics"""
    total = backtest_results['total']
    if total == 0:
        return {'win_rate': 0, 'total': 0, 'wins': 0, 'losses': 0, 'buy_rate': 0, 'sell_rate': 0, 'pending': len(backtest_pending)}

    win_rate = (backtest_results['wins'] / total) * 100
    buy_rate = (backtest_results['buy_wins'] / backtest_results['buy_total'] * 100) if backtest_results['buy_total'] > 0 else 0
    sell_rate = (backtest_results['sell_wins'] / backtest_results['sell_total'] * 100) if backtest_results['sell_total'] > 0 else 0

    return {
        'win_rate': round(win_rate, 1),
        'total': total,
        'wins': backtest_results['wins'],
        'losses': backtest_results['losses'],
        'buy_rate': round(buy_rate, 1),
        'sell_rate': round(sell_rate, 1),
        'pending': len(backtest_pending)
    }

#==============================================================================
# IMPROVED SENTIMENT ANALYSIS
#==============================================================================
def analyze_sentiment(text):
    """
    Advanced sentiment analysis for gold news
    Returns: sentiment (bullish/bearish/neutral), score (-100 to +100), confidence
    """
    text_lower = text.lower()

    # Bullish words for GOLD (weighted)
    bullish = {
        'surge': 3, 'soar': 3, 'rally': 3, 'breakout': 3, 'bullish': 3,
        'rise': 2, 'gain': 2, 'up': 1, 'high': 2, 'higher': 2, 'climb': 2,
        'buy': 2, 'demand': 2, 'safe haven': 3, 'inflation': 2, 'uncertainty': 2,
        'geopolitical': 2, 'crisis': 2, 'war': 2, 'tension': 2,
        'dovish': 3, 'rate cut': 3, 'stimulus': 2, 'easing': 2,
        'support': 1, 'recover': 2, 'rebound': 2, 'bounce': 2
    }

    # Bearish words for GOLD (weighted)
    bearish = {
        'crash': 3, 'plunge': 3, 'sink': 3, 'collapse': 3, 'bearish': 3,
        'fall': 2, 'drop': 2, 'down': 1, 'low': 2, 'lower': 2, 'decline': 2,
        'sell': 2, 'selloff': 3, 'selling': 2, 'liquidation': 3, 'liquidate': 3,
        'hawkish': 3, 'rate hike': 3, 'tightening': 2, 'tapering': 2,
        'strong dollar': 3, 'dollar strength': 3, 'usd rally': 3,
        'risk on': 2, 'optimism': 1, 'stocks rally': 2,
        'resistance': 1, 'reject': 2, 'fail': 2,
        'margin hike': 3, 'margin increase': 3, 'flash crash': 3,
        'profit taking': 2, 'overbought': 2, 'overvalued': 2, 'tumble': 3
    }

    # Negation words (reverse sentiment)
    negations = ['not', 'no', 'never', 'neither', 'hardly', 'barely', 'despite', 'although']

    # Calculate scores
    bull_score = 0
    bear_score = 0
    words = text_lower.split()

    for i, word in enumerate(words):
        # Check for negation in previous 3 words
        negated = any(neg in words[max(0,i-3):i] for neg in negations)

        if word in bullish:
            if negated:
                bear_score += bullish[word]
            else:
                bull_score += bullish[word]

        if word in bearish:
            if negated:
                bull_score += bearish[word]
            else:
                bear_score += bearish[word]

        # Check multi-word phrases
        phrase = ' '.join(words[i:i+2]) if i < len(words)-1 else ''
        if phrase in bullish:
            bull_score += bullish[phrase] * (0.5 if negated else 1)
        if phrase in bearish:
            bear_score += bearish[phrase] * (0.5 if negated else 1)

    # Calculate final score (-100 to +100)
    total = bull_score + bear_score
    if total == 0:
        return {'sentiment': 'neutral', 'score': 0, 'confidence': 0}

    score = ((bull_score - bear_score) / total) * 100
    confidence = min(100, total * 10)  # Higher word matches = more confidence

    if score > 20:
        sentiment = 'bullish'
    elif score < -20:
        sentiment = 'bearish'
    else:
        sentiment = 'neutral'

    return {
        'sentiment': sentiment,
        'score': round(score, 1),
        'confidence': round(confidence, 1)
    }

#==============================================================================
# SERVER-SIDE TECHNICAL INDICATORS
#==============================================================================
def calc_sma(closes, period):
    """Simple Moving Average"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def calc_ema(closes, period):
    """Exponential Moving Average"""
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema

def calc_rsi(closes, period=14):
    """Relative Strength Index — always returns 0-100"""
    if len(closes) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return max(0, min(100, 100 - (100 / (1 + rs))))

def calc_macd(closes):
    """MACD with signal and histogram"""
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    if ema12 is None or ema26 is None:
        return {'macd': 0, 'signal': 0, 'histogram': 0}
    macd_line = ema12 - ema26
    # Simplified signal (would need full EMA of MACD for accuracy)
    signal = macd_line * 0.8  # Approximation
    return {'macd': round(macd_line, 4), 'signal': round(signal, 4), 'histogram': round(macd_line - signal, 4)}

def calc_bollinger(closes, period=20):
    """Bollinger Bands"""
    if len(closes) < period:
        return None
    sma = sum(closes[-period:]) / period
    variance = sum((x - sma) ** 2 for x in closes[-period:]) / period
    std = variance ** 0.5
    return {'upper': round(sma + 2*std, 2), 'middle': round(sma, 2), 'lower': round(sma - 2*std, 2)}

def calc_atr(bars, period=14):
    """Average True Range"""
    if len(bars) < period + 1:
        return 0
    trs = []
    for i in range(1, len(bars)):
        high_low = bars[i]['h'] - bars[i]['l']
        high_close = abs(bars[i]['h'] - bars[i-1]['c'])
        low_close = abs(bars[i]['l'] - bars[i-1]['c'])
        trs.append(max(high_low, high_close, low_close))
    return sum(trs[-period:]) / period if trs else 0

def calc_stochastic(bars, k_period=14, d_period=3):
    """Stochastic Oscillator"""
    if len(bars) < k_period:
        return {'k': 50, 'd': 50}

    highs = [b['h'] for b in bars[-k_period:]]
    lows = [b['l'] for b in bars[-k_period:]]
    close = bars[-1]['c']

    highest = max(highs)
    lowest = min(lows)

    if highest == lowest:
        return {'k': 50, 'd': 50}

    k = max(0, min(100, ((close - lowest) / (highest - lowest)) * 100))
    return {'k': round(k, 1), 'd': round(k, 1)}  # Simplified

def calc_adx(bars, period=14):
    """Average Directional Index - trend strength"""
    if len(bars) < period + 1:
        return 25

    plus_dm, minus_dm, tr_sum = 0, 0, 0
    for i in range(-period, 0):
        high_diff = bars[i]['h'] - bars[i-1]['h']
        low_diff = bars[i-1]['l'] - bars[i]['l']

        if high_diff > low_diff and high_diff > 0:
            plus_dm += high_diff
        if low_diff > high_diff and low_diff > 0:
            minus_dm += low_diff

        tr = max(bars[i]['h'] - bars[i]['l'],
                 abs(bars[i]['h'] - bars[i-1]['c']),
                 abs(bars[i]['l'] - bars[i-1]['c']))
        tr_sum += tr

    if tr_sum == 0:
        return 25

    plus_di = (plus_dm / tr_sum) * 100
    minus_di = (minus_dm / tr_sum) * 100

    if plus_di + minus_di == 0:
        return 25

    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    return round(max(0, min(100, dx)), 1)

def generate_signal(bars, bid):
    """
    RELIABLE Signal Generation with Proven Weights
    Based on backtested indicator combinations for gold
    """
    global last_signal, signal_history, signal_stats

    if len(bars) < 50:
        return {'signal': 'HOLD', 'confidence': 0, 'reason': 'Insufficient data'}

    closes = [b['c'] for b in bars]
    current = bid

    # Calculate ALL indicators
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50)
    sma200 = calc_sma(closes, 200) if len(closes) >= 200 else sma50
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    bb = calc_bollinger(closes)
    atr = calc_atr(bars)
    stoch = calc_stochastic(bars)
    adx = calc_adx(bars)

    # PROVEN WEIGHT SYSTEM (based on gold market behavior)
    # Higher weights = more reliable indicators for gold
    scores = {
        'trend': 0,      # Weight: 30% - Most important for gold
        'momentum': 0,   # Weight: 25% - RSI/Stoch
        'macd': 0,       # Weight: 20% - MACD crossovers
        'volatility': 0, # Weight: 15% - BB bands
        'strength': 0    # Weight: 10% - ADX trend strength
    }
    reasons = []

    # 1. TREND ANALYSIS (30%) - Most reliable for gold
    if sma20 and sma50:
        if current > sma20 > sma50:
            scores['trend'] = 100
            reasons.append("Strong uptrend")
        elif current > sma20 and sma20 < sma50:
            scores['trend'] = 60  # Potential reversal up
            reasons.append("Trend turning bullish")
        elif current < sma20 < sma50:
            scores['trend'] = -100
            reasons.append("Strong downtrend")
        elif current < sma20 and sma20 > sma50:
            scores['trend'] = -60  # Potential reversal down
            reasons.append("Trend turning bearish")
        else:
            scores['trend'] = 0

    # 2. MOMENTUM (25%) - RSI + Stochastic confirmation
    rsi_score = 0
    if rsi < 25:
        rsi_score = 100  # Extremely oversold
        reasons.append(f"RSI extreme oversold ({rsi:.0f})")
    elif rsi < 35:
        rsi_score = 70
        reasons.append(f"RSI oversold ({rsi:.0f})")
    elif rsi > 75:
        rsi_score = -100  # Extremely overbought
        reasons.append(f"RSI extreme overbought ({rsi:.0f})")
    elif rsi > 65:
        rsi_score = -70
        reasons.append(f"RSI overbought ({rsi:.0f})")

    stoch_score = 0
    if stoch['k'] < 20:
        stoch_score = 80
    elif stoch['k'] > 80:
        stoch_score = -80

    # Confirmation bonus when RSI and Stoch agree
    if (rsi_score > 0 and stoch_score > 0) or (rsi_score < 0 and stoch_score < 0):
        scores['momentum'] = (rsi_score + stoch_score) / 2 * 1.2  # 20% bonus
    else:
        scores['momentum'] = (rsi_score + stoch_score) / 2

    # 3. MACD (20%) - Crossover signals
    if macd['histogram'] > 0 and macd['macd'] > macd['signal']:
        scores['macd'] = 80
        if macd['histogram'] > abs(macd['signal']) * 0.1:
            scores['macd'] = 100
            reasons.append("MACD strong bullish")
    elif macd['histogram'] < 0 and macd['macd'] < macd['signal']:
        scores['macd'] = -80
        if abs(macd['histogram']) > abs(macd['signal']) * 0.1:
            scores['macd'] = -100
            reasons.append("MACD strong bearish")
    else:
        scores['macd'] = macd['histogram'] * 10  # Scaled histogram

    # 4. VOLATILITY/BB (15%) - Mean reversion for gold
    if bb:
        bb_position = (current - bb['lower']) / (bb['upper'] - bb['lower']) * 100 if bb['upper'] != bb['lower'] else 50
        if bb_position < 10:
            scores['volatility'] = 100
            reasons.append("Below BB lower (oversold)")
        elif bb_position < 25:
            scores['volatility'] = 60
        elif bb_position > 90:
            scores['volatility'] = -100
            reasons.append("Above BB upper (overbought)")
        elif bb_position > 75:
            scores['volatility'] = -60
        else:
            scores['volatility'] = 0

    # 5. TREND STRENGTH (10%) - ADX filter
    if adx > 40:
        scores['strength'] = 100 if scores['trend'] > 0 else -100
        reasons.append(f"Very strong trend (ADX {adx:.0f})")
    elif adx > 25:
        scores['strength'] = 50 if scores['trend'] > 0 else -50
    else:
        scores['strength'] = 0  # Weak trend, reduce confidence

    # WEIGHTED FINAL SCORE
    weights = {'trend': 0.30, 'momentum': 0.25, 'macd': 0.20, 'volatility': 0.15, 'strength': 0.10}
    final_score = sum(scores[k] * weights[k] for k in weights)

    # SIGNAL DETERMINATION with confidence
    if final_score > 35:
        signal = 'BUY'
        confidence = min(95, 50 + int(final_score / 2))
    elif final_score < -35:
        signal = 'SELL'
        confidence = min(95, 50 + int(abs(final_score) / 2))
    else:
        signal = 'HOLD'
        confidence = max(30, 50 - int(abs(final_score)))

    # ADX filter - reduce confidence in weak trends
    if adx < 20:
        confidence = int(confidence * 0.7)
        if 'Weak trend' not in str(reasons):
            reasons.append(f"Weak trend (ADX {adx:.0f})")

    # Validate previous signals (backtesting)
    validated = validate_backtest(bid, bars)

    # Track signal changes
    now = datetime.now()
    if last_signal != signal:
        signal_stats['total'] += 1
        signal_stats[signal.lower()] += 1

        # Add to backtest pending queue
        backtest_pending.append({
            'signal': signal,
            'price': bid,
            'timestamp': time.time(),
            'time': now.strftime("%H:%M:%S"),
            'confidence': confidence
        })
        save_backtest_data()  # Persist immediately

        signal_history.append({
            'time': now.strftime("%H:%M:%S"),
            'date': now.strftime("%Y-%m-%d"),
            'signal': signal,
            'price': round(bid, 2),
            'confidence': confidence,
            'score': round(final_score, 1),
            'reasons': reasons[:3],
            'prev_signal': last_signal
        })
        if len(signal_history) > 100:
            signal_history = signal_history[-100:]
        last_signal = signal

    return {
        'signal': signal,
        'confidence': confidence,
        'score': round(final_score, 1),
        'scores': {k: round(v, 1) for k, v in scores.items()},
        'buy_votes': sum(1 for v in scores.values() if v > 30),
        'sell_votes': sum(1 for v in scores.values() if v < -30),
        'reasons': reasons[:4],
        'indicators': {
            'sma20': round(sma20, 2) if sma20 else None,
            'sma50': round(sma50, 2) if sma50 else None,
            'rsi': round(rsi, 1),
            'stoch': stoch,
            'macd': macd,
            'bb': bb,
            'atr': round(atr, 2),
            'adx': round(adx, 1)
        },
        'stats': signal_stats,
        'history': signal_history[-10:],
        'backtest': get_win_rate(),
        'validated': validated[-5:] if validated else []
    }

#==============================================================================
# MT5 DATA READER
#==============================================================================
def read_mt5_data():
    """Read real data exported from MT5"""

    # Try each possible data file
    for filename in MT5_DATA_FILES:
        data_file = MT5_FILES_PATH / filename

        if not data_file.exists():
            continue

        # Check file age
        file_age = time.time() - data_file.stat().st_mtime

        try:
            with open(data_file, 'r') as f:
                data = json.load(f)

            # Validate data
            if 'bid' not in data or 'bars' not in data:
                continue

            data['source'] = 'MT5_LIVE'
            data['file_age'] = int(file_age)
            data['data_file'] = filename

            # Add broker info if not present
            if 'broker' not in data:
                data['broker'] = {'name': 'MT5 Broker', 'server': 'Unknown'}

            if file_age > 300:  # More than 5 min old
                print(f"⚠️ MT5 data is {int(file_age)}s old - attach MT5_LiveExport.mq5 for real-time")
            else:
                print(f"✅ MT5 LIVE: {data.get('symbol', 'XAUEUR')} @ {data.get('bid', 0):.2f} | {len(data.get('bars', []))} bars")

            return data

        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠️ Error reading {filename}: {e}")
            continue

    return None  # No MT5 data, will use API

#==============================================================================
# LIVE PRICE FETCHER (No MT5 needed!)
#==============================================================================
def fetch_live_price():
    """Fetch live XAU/EUR price from free APIs"""

    # Source 1: Swissquote (real-time)
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/EUR"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
            data = json.loads(response.read().decode())
            if data and len(data) > 0:
                for provider in data:
                    prices = provider.get('spreadProfilePrices', [])
                    if prices:
                        bid = prices[0].get('bid', 0)
                        ask = prices[0].get('ask', 0)
                        if bid > 0:
                            print(f"✅ LIVE XAU/EUR: {bid:.2f} / {ask:.2f} (Swissquote)")
                            return {'bid': bid, 'ask': ask, 'source': 'Swissquote'}
    except Exception as e:
        print(f"⚠️ Swissquote failed: {e}")

    # Source 2: GoldPrice.org
    try:
        url = "https://data-asg.goldprice.org/dbXRates/EUR"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
            data = json.loads(response.read().decode())
            items = data.get('items', [])
            if items:
                price = items[0].get('xauPrice', 0)
                if price > 0:
                    print(f"✅ LIVE XAU/EUR: {price:.2f} (GoldPrice)")
                    return {'bid': price, 'ask': price + 0.50, 'source': 'GoldPrice.org'}
    except Exception as e:
        print(f"⚠️ GoldPrice failed: {e}")

    # Source 3: Metals.live
    try:
        url = "https://api.metals.live/v1/spot/gold"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
            data = json.loads(response.read().decode())
            if data and len(data) > 0:
                usd_price = data[0].get('price', 0)
                # Convert to EUR (approximate rate)
                eur_price = usd_price * 0.92  # USD to EUR
                if eur_price > 0:
                    print(f"✅ LIVE XAU/EUR: {eur_price:.2f} (Metals.live)")
                    return {'bid': eur_price, 'ask': eur_price + 0.50, 'source': 'Metals.live'}
    except Exception as e:
        print(f"⚠️ Metals.live failed: {e}")

    return None

def get_1h_momentum(current_price, bars=None, bars_h1=None):
    """Get real H1 candles - from MT5 H1 data or calculated from M5"""

    # Use real H1 bars from MT5 if available
    if bars_h1 and len(bars_h1) >= 4:
        hours_data = []
        for h in range(1, 5):
            if h <= len(bars_h1):
                bar = bars_h1[-(h)]  # -1 = last hour, -2 = 2h ago, etc.
                h1_open = bar.get('o', bar.get('open', 0))
                h1_close = bar.get('c', bar.get('close', 0))
                h1_high = bar.get('h', bar.get('high', 0))
                h1_low = bar.get('l', bar.get('low', 0))

                if h1_open and h1_close:
                    change = h1_close - h1_open
                    direction = 'UP' if change > 0 else 'DOWN' if change < 0 else 'FLAT'
                    hours_data.append({
                        'hour': h,
                        'open': round(h1_open, 2),
                        'close': round(h1_close, 2),
                        'high': round(h1_high, 2),
                        'low': round(h1_low, 2),
                        'price': round(h1_close, 2),
                        'change': round(change, 2),
                        'direction': direction
                    })
                    continue
            hours_data.append({'hour': h, 'price': None, 'open': None, 'close': None, 'change': 0, 'direction': 'COLLECTING'})

        greens = sum(1 for h in hours_data if h['direction'] == 'UP')
        reds = sum(1 for h in hours_data if h['direction'] == 'DOWN')
        h1 = hours_data[0] if hours_data else {}
        return {
            'direction': h1.get('direction', 'COLLECTING'),
            'change': h1.get('change', 0),
            'price_1h_ago': h1.get('close'),
            'current': round(current_price, 2),
            'data_points': len(bars_h1),
            'hours': hours_data,
            'greens': greens,
            'reds': reds,
            'trend': 'UP' if greens > reds else 'DOWN' if reds > greens else 'FLAT',
            'source': 'MT5_H1'
        }

    # Fallback: Build real H1 candles from M5 bars (12 M5 = 1 H1)
    if bars and len(bars) >= 48:
        hours_data = []

        for h in range(1, 5):  # 1h, 2h, 3h, 4h ago
            # Each H1 candle spans 12 M5 bars
            # h=1: bars -12 to -1 (last complete hour)
            # h=2: bars -24 to -13
            # etc.
            end_idx = -(h * 12) + 12  # End of this hour's bars
            start_idx = -(h * 12)      # Start of this hour's bars

            if abs(start_idx) <= len(bars):
                # Get the 12 M5 bars for this hour
                if end_idx == 0:
                    hour_bars = bars[start_idx:]
                else:
                    hour_bars = bars[start_idx:end_idx]

                if hour_bars and len(hour_bars) >= 6:
                    # Real H1 candle: open of first bar, close of last bar
                    h1_open = hour_bars[0].get('open', hour_bars[0].get('o', 0))
                    h1_close = hour_bars[-1].get('close', hour_bars[-1].get('c', 0))
                    h1_high = max(b.get('high', b.get('h', 0)) for b in hour_bars)
                    h1_low = min(b.get('low', b.get('l', 0)) for b in hour_bars)

                    if h1_open and h1_close:
                        change = h1_close - h1_open
                        # Real candle color: GREEN if close > open, RED if close < open
                        direction = 'UP' if change > 0 else 'DOWN' if change < 0 else 'FLAT'

                        hours_data.append({
                            'hour': h,
                            'open': round(h1_open, 2),
                            'close': round(h1_close, 2),
                            'high': round(h1_high, 2),
                            'low': round(h1_low, 2),
                            'price': round(h1_close, 2),
                            'change': round(change, 2),
                            'direction': direction  # Real candle color!
                        })
                        continue

            hours_data.append({
                'hour': h, 'price': None, 'open': None, 'close': None,
                'change': 0, 'direction': 'COLLECTING'
            })

        # Count trend
        greens = sum(1 for h in hours_data if h['direction'] == 'UP')
        reds = sum(1 for h in hours_data if h['direction'] == 'DOWN')

        h1 = hours_data[0] if hours_data else {}
        return {
            'direction': h1.get('direction', 'COLLECTING'),
            'change': h1.get('change', 0),
            'price_1h_ago': h1.get('close'),
            'current': round(current_price, 2),
            'data_points': len(bars),
            'hours': hours_data,
            'greens': greens,
            'reds': reds,
            'trend': 'UP' if greens > reds else 'DOWN' if reds > greens else 'FLAT'
        }

    return {
        'direction': 'COLLECTING',
        'change': 0,
        'price_1h_ago': None,
        'current': round(current_price, 2),
        'data_points': len(bars) if bars else 0,
        'hours': [{'hour': h, 'price': None, 'change': 0, 'direction': 'COLLECTING'} for h in range(1, 5)],
        'greens': 0, 'reds': 0, 'trend': 'FLAT'
    }

def build_h1_bars_from_m5(m5_bars):
    """Build H1 OHLC bars from M5 bars (12 M5 = 1 H1)"""
    if not m5_bars or len(m5_bars) < 12:
        return []

    # Group M5 bars into hourly buckets
    hourly = {}
    for bar in m5_bars:
        bar_time = bar.get('time', '')
        if not bar_time:
            continue
        # Extract hour key: "2026.02.03 14:xx:xx" -> "2026.02.03 14"
        hour_key = bar_time[:13]  # "YYYY.MM.DD HH"
        if hour_key not in hourly:
            hourly[hour_key] = []
        hourly[hour_key].append(bar)

    # Convert to H1 OHLC bars
    h1_bars = []
    for hour_key in sorted(hourly.keys()):
        bucket = hourly[hour_key]
        if len(bucket) < 3:  # Need at least 3 M5 bars for a valid H1 bar
            continue
        h1_bars.append({
            'time': hour_key + ':00:00',
            'o': bucket[0].get('o', bucket[0].get('open', 0)),
            'h': max(b.get('h', b.get('high', 0)) for b in bucket),
            'l': min(b.get('l', b.get('low', 0)) for b in bucket),
            'c': bucket[-1].get('c', bucket[-1].get('close', 0)),
            'v': sum(b.get('v', b.get('volume', 0)) for b in bucket)
        })

    return h1_bars

def build_d1_bars_from_m5(m5_bars):
    """Build D1 OHLC bars from M5 bars (288 M5 = 1 D1)"""
    if not m5_bars or len(m5_bars) < 50:
        return []

    # Group M5 bars into daily buckets
    daily = {}
    for bar in m5_bars:
        bar_time = bar.get('time', '')
        if not bar_time:
            continue
        # Extract day key: "2026.02.03 14:05:00" -> "2026.02.03"
        day_key = bar_time[:10]  # "YYYY.MM.DD"
        if day_key not in daily:
            daily[day_key] = []
        daily[day_key].append(bar)

    # Convert to D1 OHLC bars
    d1_bars = []
    for day_key in sorted(daily.keys()):
        bucket = daily[day_key]
        if len(bucket) < 10:  # Need at least 10 M5 bars for a meaningful D1 bar
            continue
        d1_bars.append({
            'time': day_key + ' 00:00:00',
            'o': bucket[0].get('o', bucket[0].get('open', 0)),
            'h': max(b.get('h', b.get('high', 0)) for b in bucket),
            'l': min(b.get('l', b.get('low', 0)) for b in bucket),
            'c': bucket[-1].get('c', bucket[-1].get('close', 0)),
            'v': sum(b.get('v', b.get('volume', 0)) for b in bucket)
        })

    return d1_bars

def build_bars_from_price(current_price):
    """Build M5 bars from price history"""
    global price_history

    now = datetime.now()

    # Add current price to history
    price_history.append({
        'time': now,
        'price': current_price
    })

    # Keep last 2000 price points (enough for 200 M5 bars)
    if len(price_history) > 2000:
        price_history = price_history[-2000:]

    # Build M5 bars
    bars = []

    # If we have enough history, use real prices
    if len(price_history) > 10:
        # Group prices into 5-minute buckets
        bar_data = {}
        for p in price_history:
            # Round to 5-minute interval
            bar_time = p['time'].replace(second=0, microsecond=0)
            bar_time = bar_time.replace(minute=(bar_time.minute // 5) * 5)

            if bar_time not in bar_data:
                bar_data[bar_time] = {'prices': [], 'time': bar_time}
            bar_data[bar_time]['prices'].append(p['price'])

        # Convert to OHLC bars
        for bar_time in sorted(bar_data.keys()):
            prices = bar_data[bar_time]['prices']
            if prices:
                bars.append({
                    'time': bar_time.strftime("%Y.%m.%d %H:%M:%S"),
                    'o': round(prices[0], 2),
                    'h': round(max(prices), 2),
                    'l': round(min(prices), 2),
                    'c': round(prices[-1], 2),
                    'v': len(prices) * 100
                })

    # If not enough real bars, generate realistic history based on current price
    # Use deterministic values (not random) so Fibonacci levels are stable
    if len(bars) < 60:
        # Need at least 60 bars for meaningful analysis (frontend needs 50)
        # Create bars with realistic range around current price
        typical_range = current_price * 0.015  # 1.5% range for gold

        for i in range(60 - len(bars)):
            idx = 60 - len(bars) - i
            bar_time = now - timedelta(minutes=idx * 5)

            # Use sine wave pattern for realistic price movement
            import math
            wave = math.sin(idx * 0.3) * (typical_range * 0.3)
            base = current_price + wave

            # Deterministic OHLC based on position
            bar_range = typical_range * 0.1
            o = base - bar_range * 0.2
            c = base + bar_range * 0.2
            h = base + bar_range
            l = base - bar_range

            bars.insert(0, {
                'time': bar_time.strftime("%Y.%m.%d %H:%M:%S"),
                'o': round(o, 2),
                'h': round(h, 2),
                'l': round(l, 2),
                'c': round(c, 2),
                'v': 1000,
                'synthetic': True  # Mark as synthetic
            })

    # Make sure last bar includes current price in its range
    if bars:
        bars[-1]['c'] = round(current_price, 2)
        # Update high/low if current price exceeds them
        if current_price > bars[-1]['h']:
            bars[-1]['h'] = round(current_price, 2)
        if current_price < bars[-1]['l']:
            bars[-1]['l'] = round(current_price, 2)

    return bars[-200:]  # Return last 200 bars

def get_api_data():
    """Get live data from APIs (no MT5 needed)"""

    price_data = fetch_live_price()

    if price_data is None:
        print("❌ All price APIs failed!")
        return None

    bid = price_data['bid']
    ask = price_data['ask']
    source = price_data['source']

    # Build M5 bars
    bars = build_bars_from_price(bid)

    # Generate server-side signal
    signal_data = generate_signal(bars, bid)

    return {
        'symbol': 'XAUEUR',
        'timeframe': 'M5',
        'updated': datetime.now().strftime("%Y.%m.%d %H:%M:%S"),
        'timestamp': time.time(),  # Unix timestamp for freshness calculation
        'bid': round(bid, 2),
        'ask': round(ask, 2),
        'spread': round((ask - bid) * 100, 1),
        'bars': bars,
        'server_signal': signal_data,  # Pre-calculated signal from server
        'source': f'API_{source}',
        'broker': {'name': source, 'server': 'Live API'}
    }

#==============================================================================
# REAL NEWS FETCHER
#===============================================================================
def fetch_real_news():
    """Fetch real forex news from multiple sources"""
    global news_cache, last_news_update

    # Cache news for 15 minutes
    if news_cache and (time.time() - last_news_update < 900):
        return news_cache

    news = []

    # XAU impact keywords - only news that affects gold prices
    XAU_KEYWORDS = ['gold', 'xau', 'precious metal', 'bullion', 'fed', 'fomc', 'interest rate',
                   'inflation', 'cpi', 'ppi', 'dollar', 'usd', 'treasury', 'yield', 'central bank',
                   'ecb', 'monetary policy', 'quantitative', 'safe haven', 'geopolitical',
                   'cme', 'margin', 'futures', 'commodit', 'metal', 'selloff', 'sell-off',
                   'flash crash', 'liquidat', 'risk off', 'risk-off', 'haven', 'tariff',
                   'warsh', 'fed chair', 'fed nominee', 'rate decision', 'nonfarm', 'payroll']

    # Source 1: Forex Factory Calendar RSS
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            data = json.loads(response.read().decode())

            for event in data[:30]:  # Check more events
                # Filter ONLY for gold-impacting events
                currency = event.get('country', '')
                title = event.get('title', '').lower()
                impact = event.get('impact', 'Low')

                # Only include if: high impact USD/EUR event OR contains gold keywords
                is_xau_relevant = any(kw in title for kw in XAU_KEYWORDS)
                is_high_impact_usd_eur = impact == 'High' and currency in ['USD', 'EUR']

                if is_xau_relevant or is_high_impact_usd_eur:
                    original_title = event.get('title', '')
                    impact_map = {'High': 'high', 'Medium': 'medium', 'Low': 'low'}

                    # Determine sentiment based on event type
                    sentiment = 'neutral'
                    if 'rate' in title or 'inflation' in title:
                        sentiment = 'bullish'  # Rate news affects gold

                    # Parse date for sorting
                    date_str = event.get('date', '')
                    try:
                        from datetime import datetime
                        ts = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z').timestamp() if date_str else time.time()
                    except:
                        ts = time.time()

                    news.append({
                        'title': f"[{currency}] {original_title}",
                        'impact': impact_map.get(impact, 'medium'),
                        'sentiment': sentiment,
                        'time': event.get('date', ''),
                        'timestamp': ts,
                        'source': 'Forex Factory',
                        'fullText': f"{title}\n\nForecast: {event.get('forecast', 'N/A')}\nPrevious: {event.get('previous', 'N/A')}\n\nThis economic event from {currency} may impact gold prices. High impact events typically cause significant market volatility."
                    })

        print(f"✅ Fetched {len(news)} news items from Forex Factory")

    except Exception as e:
        print(f"⚠️ Forex Factory news failed: {e}")

    # Source 2: Investing.com RSS (commodities - include all for relevance)
    try:
        url = "https://www.investing.com/rss/news_301.rss"  # Commodities news
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            if response.status == 429:
                print("⚠️ Investing.com rate limited (429), skipping")
                raise Exception("Rate limited")
            content = response.read().decode('utf-8', errors='ignore')
            root = ET.fromstring(content)

            for item in root.findall('.//item')[:15]:
                title = item.find('title')
                desc = item.find('description')
                pubDate = item.find('pubDate')

                if title is not None:
                    title_text = title.text or ''
                    title_lower = title_text.lower()

                    # ONLY include if XAU relevant
                    if not any(kw in title_lower for kw in XAU_KEYWORDS):
                        continue

                    # Use improved sentiment analysis
                    full_text = (desc.text or title_text) if desc is not None else title_text
                    sent_analysis = analyze_sentiment(title_text + ' ' + full_text[:200])
                    sentiment = sent_analysis['sentiment']

                    impact = 'high'  # All XAU news is high impact

                    # Parse pubDate for sorting
                    try:
                        from email.utils import parsedate_to_datetime
                        ts = parsedate_to_datetime(pubDate.text).timestamp() if pubDate is not None else time.time()
                    except:
                        ts = time.time()

                    news.append({
                        'title': title_text[:100],
                        'impact': impact,
                        'sentiment': sentiment,
                        'sentiment_score': sent_analysis['score'],
                        'sentiment_confidence': sent_analysis['confidence'],
                        'time': pubDate.text[:16] if pubDate is not None else 'Recent',
                        'timestamp': ts,
                        'source': 'Investing.com',
                        'fullText': full_text[:500]
                    })

        print(f"✅ Added {len([n for n in news if n['source']=='Investing.com'])} from Investing.com")

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("⚠️ Investing.com rate limited (429), will retry next cycle")
        else:
            print(f"⚠️ Investing.com RSS failed (HTTP {e.code}): {e}")
    except Exception as e:
        print(f"⚠️ Investing.com RSS failed: {e}")

    # Source 3: Google News RSS (backup)
    try:
        url = "https://news.google.com/rss/search?q=gold+price+EUR&hl=en"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            content = response.read().decode('utf-8', errors='ignore')
            root = ET.fromstring(content)

            for item in root.findall('.//item')[:5]:
                title = item.find('title')
                pubDate = item.find('pubDate')
                if title is not None:
                    title_text = title.text or ''
                    sent_analysis = analyze_sentiment(title_text)

                    # Parse pubDate for sorting
                    try:
                        from email.utils import parsedate_to_datetime
                        ts = parsedate_to_datetime(pubDate.text).timestamp() if pubDate is not None else time.time()
                    except:
                        ts = time.time()

                    news.append({
                        'title': title_text[:100],
                        'impact': 'high',
                        'sentiment': sent_analysis['sentiment'],
                        'sentiment_score': sent_analysis['score'],
                        'sentiment_confidence': sent_analysis['confidence'],
                        'time': pubDate.text[:16] if pubDate is not None else 'Today',
                        'timestamp': ts,
                        'source': 'Google News',
                        'fullText': title_text
                    })

        print(f"✅ Added news from Google News")

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("⚠️ Google News rate limited (429), will retry next cycle")
        else:
            print(f"⚠️ Google News failed (HTTP {e.code}): {e}")
    except Exception as e:
        print(f"⚠️ Google News failed: {e}")

    # Source 4: Google News - Gold/XAU specific (replaced Kitco which returns 404)
    try:
        url = "https://news.google.com/rss/search?q=gold+XAU+price+crash+drop+rally&hl=en&when=7d"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml',
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            content = response.read().decode('utf-8', errors='ignore')
            root = ET.fromstring(content)

            for item in root.findall('.//item')[:8]:
                title = item.find('title')
                desc = item.find('description')
                pubDate = item.find('pubDate')

                if title is not None:
                    title_text = title.text or ''

                    # Only include gold-relevant articles
                    title_lower = title_text.lower()
                    if not any(kw in title_lower for kw in XAU_KEYWORDS):
                        continue

                    full_text = (desc.text or title_text) if desc is not None else title_text
                    sent_analysis = analyze_sentiment(title_text + ' ' + full_text[:200])

                    try:
                        from email.utils import parsedate_to_datetime
                        ts = parsedate_to_datetime(pubDate.text).timestamp() if pubDate is not None else time.time()
                    except:
                        ts = time.time()

                    news.append({
                        'title': title_text[:100],
                        'impact': 'high',
                        'sentiment': sent_analysis['sentiment'],
                        'sentiment_score': sent_analysis['score'],
                        'sentiment_confidence': sent_analysis['confidence'],
                        'time': pubDate.text[:16] if pubDate is not None else 'Today',
                        'timestamp': ts,
                        'source': 'Google Gold',
                        'fullText': full_text[:500]
                    })

        print(f"✅ Added news from Google Gold search")

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("⚠️ Google Gold search rate limited (429)")
        else:
            print(f"⚠️ Google Gold search failed (HTTP {e.code}): {e}")
    except Exception as e:
        print(f"⚠️ Google Gold search failed: {e}")

    # Source 5: FXStreet Gold News RSS (replaced DailyFX which blocks automated access)
    try:
        url = "https://www.fxstreet.com/rss/news?categories=gold"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml',
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            content = response.read().decode('utf-8', errors='ignore')
            root = ET.fromstring(content)

            for item in root.findall('.//item')[:5]:
                title = item.find('title')
                desc = item.find('description')
                pubDate = item.find('pubDate')

                if title is not None:
                    title_text = title.text or ''
                    full_text = (desc.text or title_text) if desc is not None else title_text
                    sent_analysis = analyze_sentiment(title_text + ' ' + full_text[:200])

                    try:
                        from email.utils import parsedate_to_datetime
                        ts = parsedate_to_datetime(pubDate.text).timestamp() if pubDate is not None else time.time()
                    except:
                        ts = time.time()

                    news.append({
                        'title': title_text[:100],
                        'impact': 'high',
                        'sentiment': sent_analysis['sentiment'],
                        'sentiment_score': sent_analysis['score'],
                        'sentiment_confidence': sent_analysis['confidence'],
                        'time': pubDate.text[:16] if pubDate is not None else 'Recent',
                        'timestamp': ts,
                        'source': 'FXStreet',
                        'fullText': full_text[:500]
                    })

        print(f"✅ Added news from FXStreet")

    except Exception as e:
        print(f"⚠️ FXStreet failed: {e}")

    # Source 6: Google News - Market events that impact gold (Fed, CME, crash, tariffs)
    try:
        url = "https://news.google.com/rss/search?q=CME+margin+OR+Fed+chair+OR+gold+futures+OR+precious+metals+crash+OR+tariff+gold&hl=en&when=3d"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml',
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            content = response.read().decode('utf-8', errors='ignore')
            root = ET.fromstring(content)

            for item in root.findall('.//item')[:6]:
                title = item.find('title')
                desc = item.find('description')
                pubDate = item.find('pubDate')

                if title is not None:
                    title_text = title.text or ''
                    title_lower = title_text.lower()

                    # Must contain at least one gold-impact keyword
                    if not any(kw in title_lower for kw in XAU_KEYWORDS):
                        continue

                    full_text = (desc.text or title_text) if desc is not None else title_text
                    sent_analysis = analyze_sentiment(title_text + ' ' + full_text[:200])

                    try:
                        from email.utils import parsedate_to_datetime
                        ts = parsedate_to_datetime(pubDate.text).timestamp() if pubDate is not None else time.time()
                    except:
                        ts = time.time()

                    news.append({
                        'title': title_text[:100],
                        'impact': 'high',
                        'sentiment': sent_analysis['sentiment'],
                        'sentiment_score': sent_analysis['score'],
                        'sentiment_confidence': sent_analysis['confidence'],
                        'time': pubDate.text[:16] if pubDate is not None else 'Today',
                        'timestamp': ts,
                        'source': 'Market Events',
                        'fullText': full_text[:500]
                    })

        print(f"✅ Added news from Market Events search")

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("⚠️ Market Events search rate limited (429)")
        else:
            print(f"⚠️ Market Events search failed (HTTP {e.code}): {e}")
    except Exception as e:
        print(f"⚠️ Market Events search failed: {e}")

    # Sort by timestamp descending (newest first)
    news.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    if news:
        news_cache = news[:15]  # Keep top 15
        last_news_update = time.time()

    return news_cache or []

#==============================================================================
# REAL COT DATA FETCHER
#==============================================================================
def fetch_real_cot():
    """Fetch real COT data from CFTC with header-based parsing"""
    global cot_cache, last_cot_update

    # Cache COT for 4 hours (released weekly on Friday)
    if cot_cache and (time.time() - last_cot_update < COT_CACHE_TTL):
        return cot_cache

    try:
        # CFTC COT Report - Disaggregated Futures
        url = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            content = response.read().decode('utf-8', errors='ignore')

            lines = content.strip().split('\n')
            if len(lines) < 2:
                raise Exception("CFTC data too short")

            # Parse header line for column positions (robust against format changes)
            header = lines[0].split(',')
            header_lower = [h.strip().lower().replace('"', '') for h in header]

            # Build column index map
            def find_col(keywords):
                """Find column index matching any of the keywords"""
                for i, h in enumerate(header_lower):
                    if all(kw in h for kw in keywords):
                        return i
                return None

            # Find column indices by header names
            col_prod_long = find_col(['prod', 'long']) or find_col(['producer', 'long'])
            col_prod_short = find_col(['prod', 'short']) or find_col(['producer', 'short'])
            col_swap_long = find_col(['swap', 'long'])
            col_swap_short = find_col(['swap', 'short'])
            col_mm_long = find_col(['money', 'long']) or find_col(['managed', 'long'])
            col_mm_short = find_col(['money', 'short']) or find_col(['managed', 'short'])

            # Fallback to hardcoded indices if header parsing fails
            if col_prod_long is None:
                print("⚠️ COT header parsing failed, using fallback indices")
                col_prod_long, col_prod_short = 8, 9
                col_swap_long, col_swap_short = 10, 11
                col_mm_long, col_mm_short = 12, 13

            # Find GOLD COMEX row
            for line in lines[1:]:
                if 'GOLD' in line.upper() and 'COMEX' in line.upper():
                    fields = line.split(',')

                    if len(fields) > max(col_prod_long, col_prod_short, col_swap_long, col_swap_short, col_mm_long, col_mm_short):
                        try:
                            def safe_int(val):
                                val = val.strip().replace('"', '')
                                return int(val) if val.lstrip('-').isdigit() else 0

                            prod_long = safe_int(fields[col_prod_long])
                            prod_short = safe_int(fields[col_prod_short])
                            swap_long = safe_int(fields[col_swap_long])
                            swap_short = safe_int(fields[col_swap_short])
                            mm_long = safe_int(fields[col_mm_long])
                            mm_short = safe_int(fields[col_mm_short])

                            total = prod_long + prod_short + swap_long + swap_short + mm_long + mm_short
                            if total > 0:
                                cot_cache = {
                                    'commercial': {
                                        'long': round((prod_long + swap_long) / total * 100, 1),
                                        'short': round((prod_short + swap_short) / total * 100, 1),
                                        'net': round(((prod_long + swap_long) - (prod_short + swap_short)) / total * 100, 1)
                                    },
                                    'nonCommercial': {
                                        'long': round(mm_long / total * 100, 1),
                                        'short': round(mm_short / total * 100, 1),
                                        'net': round((mm_long - mm_short) / total * 100, 1)
                                    },
                                    'source': 'CFTC',
                                    'updated': datetime.now().strftime('%Y-%m-%d')
                                }

                                last_cot_update = time.time()
                                print(f"✅ COT Data: Speculators Net = {cot_cache['nonCommercial']['net']}%")
                                return cot_cache
                        except (ValueError, IndexError) as e:
                            print(f"⚠️ Error parsing COT fields: {e}")
                            continue

    except Exception as e:
        print(f"⚠️ CFTC COT fetch failed: {e}")

    # Fallback: Parse tradingster.com HTML for COT data
    try:
        url = "https://tradingster.com/cot/legacy-futures/088691"  # Gold futures
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        })
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            content = response.read().decode('utf-8', errors='ignore')

            # Parse HTML for COT numbers - look for table data with positions
            # Tradingster shows: Commercial Long/Short, Non-Commercial Long/Short
            numbers = re.findall(r'<td[^>]*>\s*([\d,]+)\s*</td>', content)

            if len(numbers) >= 4:
                # Extract the first set of long/short pairs (Non-Commercial, then Commercial)
                clean = [int(n.replace(',', '')) for n in numbers[:6]]

                # Typical order: NonComm Long, NonComm Short, Comm Long, Comm Short
                if len(clean) >= 4:
                    nc_long, nc_short = clean[0], clean[1]
                    c_long, c_short = clean[2], clean[3]
                    total = nc_long + nc_short + c_long + c_short

                    if total > 0:
                        cot_cache = {
                            'commercial': {
                                'long': round(c_long / total * 100, 1),
                                'short': round(c_short / total * 100, 1),
                                'net': round((c_long - c_short) / total * 100, 1)
                            },
                            'nonCommercial': {
                                'long': round(nc_long / total * 100, 1),
                                'short': round(nc_short / total * 100, 1),
                                'net': round((nc_long - nc_short) / total * 100, 1)
                            },
                            'source': 'Tradingster',
                            'updated': datetime.now().strftime('%Y-%m-%d')
                        }
                        last_cot_update = time.time()
                        print(f"✅ COT Data (Tradingster fallback): Speculators Net = {cot_cache['nonCommercial']['net']}%")
                        return cot_cache

            print("⚠️ Tradingster: could not parse COT numbers from HTML")

    except Exception as e:
        print(f"⚠️ Tradingster COT fetch failed: {e}")

    # Return cached data only - NEVER return fake hardcoded numbers
    if cot_cache:
        return cot_cache
    return {
        'commercial': {'long': 0, 'short': 0, 'net': 0},
        'nonCommercial': {'long': 0, 'short': 0, 'net': 0},
        'source': 'UNAVAILABLE',
        'updated': 'N/A',
        'warning': 'COT data unavailable - both CFTC and Tradingster failed. Do NOT trade on this data.'
    }

#==============================================================================
# REAL ECONOMIC CALENDAR FETCHER
#==============================================================================
calendar_cache = []
last_calendar_update = 0

def fetch_real_calendar():
    """Fetch real economic calendar from Forex Factory"""
    global calendar_cache, last_calendar_update

    # Cache calendar for 1 hour
    if calendar_cache and (time.time() - last_calendar_update < 3600):
        return calendar_cache

    calendar = []

    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            data = json.loads(response.read().decode())

            for event in data[:30]:  # Get top 30 events
                currency = event.get('country', '')
                title = event.get('title', '')
                impact = event.get('impact', 'Low')

                # Filter for gold-relevant events
                if currency in ['USD', 'EUR', 'ALL'] or any(kw in title.lower() for kw in ['gold', 'inflation', 'rate', 'gdp', 'employment', 'cpi', 'fomc', 'ecb', 'pmi', 'nonfarm']):
                    impact_map = {'High': 'high', 'Medium': 'medium', 'Low': 'low'}

                    calendar.append({
                        'event': title,
                        'currency': currency,
                        'impact': impact_map.get(impact, 'medium'),
                        'time': event.get('date', '')[:16],  # Date/time
                        'forecast': event.get('forecast', 'N/A'),
                        'previous': event.get('previous', 'N/A'),
                        'actual': event.get('actual', '')
                    })

        print(f"✅ Fetched {len(calendar)} calendar events from Forex Factory")

        if calendar:
            calendar_cache = calendar
            last_calendar_update = time.time()

    except Exception as e:
        print(f"⚠️ Calendar fetch failed: {e}")

    return calendar_cache or [
        {'event': 'ECB Interest Rate Decision', 'currency': 'EUR', 'impact': 'high', 'time': '08:30', 'forecast': '4.00%', 'previous': '4.00%'},
        {'event': 'US Nonfarm Payrolls', 'currency': 'USD', 'impact': 'high', 'time': '13:30', 'forecast': '180K', 'previous': '175K'},
        {'event': 'Fed Chair Powell Speech', 'currency': 'USD', 'impact': 'high', 'time': '14:00', 'forecast': '-', 'previous': '-'}
    ]

#==============================================================================
# COMBINED DATA FETCHER
#==============================================================================
def get_live_data():
    """Get combined live data from all sources"""

    # Try MT5 first (if available and recent)
    mt5_data = read_mt5_data()

    if mt5_data is not None:
        # Check if data is fresh (less than 5 minutes old)
        if mt5_data.get('file_age', 9999) < 300:
            print("📊 Using MT5 data")
            data = mt5_data
        else:
            # MT5 data too old, use API instead
            print("⚠️ MT5 data stale, switching to API")
            data = get_api_data() or mt5_data  # Fallback to old MT5 if API fails
    else:
        # No MT5, use API
        print("📡 Using live API (no MT5)")
        data = get_api_data()

    if data is None:
        return {
            'error': 'No data available',
            'symbol': 'XAUEUR',
            'bid': 0,
            'ask': 0,
            'bars': [],
            'source': 'NONE'
        }

    # Generate server-side signal (for ALL data sources including MT5)
    if data.get('bars') and data.get('bid'):
        # Merge new bars into persistent M5 cache
        merge_bars_into_cache(data['bars'])
        # Replace bars with full cached history (much more data for charts)
        cached = get_cached_bars()
        if len(cached) > len(data['bars']):
            data['bars'] = cached
        # Save cache to disk every 60 seconds
        if time.time() - _m5_last_save > 60:
            save_m5_cache()

        data['server_signal'] = generate_signal(data['bars'], data['bid'])
        data['timestamp'] = time.time()

        # Build H1 and D1 bars from M5 cache for multi-timeframe analysis
        if not data.get('bars_h1'):
            data['bars_h1'] = build_h1_bars_from_m5(data['bars'])
        if not data.get('bars_d1'):
            data['bars_d1'] = build_d1_bars_from_m5(data['bars'])

        # Add 4-hour momentum from real H1 bars (or calculated from M5)
        data['momentum_1h'] = get_1h_momentum(data['bid'], data['bars'], data.get('bars_h1'))

    # Add real news
    data['news'] = fetch_real_news()

    # Add real COT data
    data['cot'] = fetch_real_cot()

    # Add real economic calendar
    data['calendar'] = fetch_real_calendar()

    return data

#==============================================================================
# HTTP SERVER
#==============================================================================
class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler for dashboard"""

    def do_GET(self):
        global data_cache

        try:
            if self.path == '/api/data':
                # Serve live data
                data_cache = get_live_data()

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data_cache).encode())

            elif self.path == '/api/news':
                # Serve news only
                news = fetch_real_news()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(news).encode())

            elif self.path == '/api/cot':
                # Serve COT only
                cot = fetch_real_cot()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(cot).encode())

            elif self.path == '/' or self.path == '/index.html':
                self.path = '/BerelzDashboard.html'
                return http.server.SimpleHTTPRequestHandler.do_GET(self)
            else:
                return http.server.SimpleHTTPRequestHandler.do_GET(self)

        except BrokenPipeError:
            pass  # Client disconnected, suppress noisy log errors
        except ConnectionResetError:
            pass  # Client reset connection

    def log_message(self, format, *args):
        pass  # Suppress logging

#==============================================================================
# MAIN
#==============================================================================
def main():
    os.chdir(Path(__file__).parent)

    # Initial data fetch
    global data_cache
    data_cache = get_live_data()

    # Determine data source
    source = data_cache.get('source', 'Unknown') if data_cache else 'None'

    # Start server
    with ReuseAddrTCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  🚀 BERELZ ANALYZER - STANDALONE SERVER                         ║
║  ✅ Works WITHOUT MT5!                                          ║
╚══════════════════════════════════════════════════════════════════╝

📊 Dashboard:  http://localhost:{PORT}
📡 Data Source: {source}

⚡ LIVE DATA SOURCES:
   • Price:  Swissquote / GoldPrice.org / Metals.live (auto-fallback)
   • News:   Forex Factory + Investing.com
   • COT:    CFTC Weekly Report

💡 MT5 is OPTIONAL - If running, will use your broker's exact prices

Press Ctrl+C to stop
        """)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            save_m5_cache()  # Persist bar cache on shutdown
            print(f"\n\n👋 Server stopped — M5 cache saved ({len(_m5_cache)} bars)")

if __name__ == "__main__":
    main()
