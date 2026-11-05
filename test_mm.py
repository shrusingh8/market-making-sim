"""Run: python -m pytest -q"""
from mm import simulate

STEPS = 20_000


def test_without_informed_flow_spread_is_pure_profit():
    r = simulate(0.1, skew=0.01, steps=STEPS, informed_rate=0.0)
    assert abs(r["adverse"]) < 0.004          # markouts are just noise
    assert r["spread"] > 0.05 and r["pnl"] > 0


def test_quoting_too_tight_loses_to_informed_traders():
    r = simulate(0.0, skew=0.01, steps=STEPS)
    assert r["adverse"] < -0.01 and r["pnl"] < 0


def test_wider_quotes_fill_less_and_get_picked_off_less():
    tight, wide = simulate(0.05, skew=0.01, steps=STEPS), simulate(0.3, skew=0.01, steps=STEPS)
    assert wide["fill_rate"] < tight["fill_rate"] / 4
    assert wide["adverse"] > tight["adverse"]   # adverse selection is negative; closer to 0 is better


def test_pnl_parts_add_up():
    r = simulate(0.12, skew=0.01, steps=STEPS)
    assert abs(r["spread"] + r["adverse"] + r["inventory"] - r["pnl"]) < 1e-12


def test_skew_keeps_inventory_small():
    free, managed = simulate(0.12, skew=0.0, steps=STEPS), simulate(0.12, skew=0.01, steps=STEPS)
    assert managed["inv_std"] < free["inv_std"] / 5
