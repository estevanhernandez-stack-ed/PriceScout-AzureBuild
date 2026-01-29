"""Quick test script for EntTelligence baseline discovery."""
import sys
sys.path.insert(0, '.')

from app.enttelligence_baseline_discovery import (
    EntTelligenceBaselineDiscoveryService,
    analyze_enttelligence_prices
)
from collections import Counter

print('=== EntTelligence Baseline Discovery Test ===')
print()

# Test analysis first
print('1. PRICE ANALYSIS')
print('-' * 60)
analysis = analyze_enttelligence_prices(company_id=1, lookback_days=30)

stats = analysis.get('overall_stats', {})
total_records = stats.get('total_records', 0)
total_theaters = stats.get('total_theaters', 0)
total_circuits = stats.get('total_circuits', 0)
date_range = stats.get('date_range', {})
avg_price = stats.get('overall_avg_price', 0) or 0

print('Overall Statistics:')
print('  Records: {:,}'.format(total_records))
print('  Theaters: {:,}'.format(total_theaters))
print('  Circuits: {}'.format(total_circuits))
print('  Date range: {} to {}'.format(date_range.get('min'), date_range.get('max')))
print('  Average price: ${:.2f}'.format(avg_price))
print()

print('Top 10 Circuits by Average Price:')
sorted_circuits = sorted(
    [(k, v) for k, v in analysis['circuits'].items() if v.get('avg_price')],
    key=lambda x: x[1]['avg_price'],
    reverse=True
)[:10]
for circuit, data in sorted_circuits:
    c_name = circuit[:40] if len(circuit) > 40 else circuit
    c_avg = data.get('avg_price', 0) or 0
    c_theaters = data.get('theater_count', 0)
    print('  {:<40} ${:>6.2f} ({} theaters)'.format(c_name, c_avg, c_theaters))
print()

print('Format Breakdown:')
for fmt, data in list(analysis['format_breakdown'].items())[:10]:
    premium = ' [PREMIUM]' if data.get('is_premium') else ''
    f_avg = data.get('avg_price', 0) or 0
    f_count = data.get('count', 0)
    print('  {:<20} ${:>6.2f} avg  {:>8,} records{}'.format(fmt or '2D/Standard', f_avg, f_count, premium))
print()

# Test baseline discovery
print('2. BASELINE DISCOVERY')
print('-' * 60)
service = EntTelligenceBaselineDiscoveryService(company_id=1)
baselines = service.discover_baselines(min_samples=5, lookback_days=30)

print('Discovered {} baselines'.format(len(baselines)))
print()

# Price distribution
if baselines:
    prices = [b['baseline_price'] for b in baselines]
    print('Baseline Price Distribution:')
    print('  Min: ${:.2f}  Max: ${:.2f}  Avg: ${:.2f}'.format(
        min(prices), max(prices), sum(prices)/len(prices)))

    volatile = [b for b in baselines if b['volatility_percent'] > 20]
    print('  High volatility (>20%): {} theaters'.format(len(volatile)))
    print()

# Group by circuit
circuit_counts = Counter(bl['circuit_name'] for bl in baselines)
print('Baselines by Circuit (top 15):')
for circuit, count in circuit_counts.most_common(15):
    # Calculate avg baseline for this circuit
    circuit_baselines = [b for b in baselines if b['circuit_name'] == circuit]
    circuit_avg = sum(b['baseline_price'] for b in circuit_baselines) / len(circuit_baselines)
    c_name = circuit[:35] if len(circuit) > 35 else circuit
    print('  {:<35} {:>4} baselines  ${:.2f} avg'.format(c_name, count, circuit_avg))
print()

# Sample baselines
print('Sample Baselines (first 10):')
for bl in baselines[:10]:
    theater = bl['theater_name'][:35]
    price = bl['baseline_price']
    circuit = bl['circuit_name'][:20] if len(bl['circuit_name']) > 20 else bl['circuit_name']
    vol = bl['volatility_percent']
    print('  {:<35} ${:>6.2f}  {:>5.1f}% vol  {}'.format(theater, price, vol, circuit))

print()
print('=== Test Complete ===')
