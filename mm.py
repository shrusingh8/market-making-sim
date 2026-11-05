"""A toy market maker: quote around the mid, get filled by noise traders and informed traders, manage inventory.

Each step:
  1. The maker quotes bid/ask = center -/+ half_spread, where center = mid - skew * inventory
     (when long, shade both quotes down to sell more and buy less).
  2. Noise traders hit each side with probability NOISE_RATE * exp(-DEPTH_DECAY * distance from mid):
     tighter quotes get more of their flow.
  3. An informed trader shows up with probability INFORMED_RATE, already knows the next mid move,
     and trades only when that move crosses the maker's quote.
  4. The mid moves by a normal step with standard deviation VOL.

PnL splits exactly into three parts (tested):
  spread captured   = sum of (mid - fill price) * maker side   -> what quoting wide earns
  adverse selection = sum of next-step mid move * maker side    -> what informed flow costs (a 1-step markout)
  inventory P&L     = old inventory * mid move                   -> the risk of holding a position

Run: python mm.py   -> prints a table, writes spread_tradeoff.png
"""
import math

import numpy as np

VOL = 0.10            # std of the per-step mid move
NOISE_RATE = 0.6      # noise-trader arrival probability per side, at zero distance
DEPTH_DECAY = 8.0     # how fast noise flow falls off as quotes widen
INFORMED_RATE = 0.15  # informed-trader arrival probability per step


def simulate(half_spread, skew=0.0, steps=20_000, seed=0, informed_rate=INFORMED_RATE):
    rng = np.random.default_rng(seed)
    # Plain Python floats in the loop: numpy scalars are ~10x slower one at a time.
    moves = rng.normal(0, VOL, steps).tolist()
    u_buy, u_sell, u_inf = (rng.random(steps).tolist() for _ in range(3))

    mid, inv = 100.0, 0
    spread_pnl = adverse = inventory_pnl = 0.0
    fills, inv_path = 0, [0] * steps
    for t in range(steps):
        center = mid - skew * inv
        bid, ask = center - half_spread, center + half_spread
        move = moves[t]

        trades = []  # maker side: +1 maker buys at bid, -1 maker sells at ask
        if u_buy[t] < NOISE_RATE * math.exp(-DEPTH_DECAY * max(ask - mid, 0)):
            trades.append(-1)                          # noise trader buys from the maker
        if u_sell[t] < NOISE_RATE * math.exp(-DEPTH_DECAY * max(mid - bid, 0)):
            trades.append(+1)                          # noise trader sells to the maker
        if u_inf[t] < informed_rate:
            if mid + move > ask:
                trades.append(-1)                      # informed buys: maker sells before a rise
            elif mid + move < bid:
                trades.append(+1)                      # informed sells: maker buys before a drop

        inventory_pnl += inv * move                    # position held from before this step
        for side in trades:
            price = bid if side > 0 else ask
            spread_pnl += side * (mid - price)
            adverse += side * move
            inv += side
        fills += len(trades)
        mid += move
        inv_path[t] = inv

    return {
        "half_spread": half_spread, "skew": skew,
        "fill_rate": fills / steps,
        "spread": spread_pnl / steps, "adverse": adverse / steps, "inventory": inventory_pnl / steps,
        "pnl": (spread_pnl + adverse + inventory_pnl) / steps,
        "inv_std": float(np.std(inv_path)), "max_abs_inv": max(map(abs, inv_path)),
    }


def sweep(half_spreads, seeds=6, **kw):
    """Average over seeds: one path is too noisy to read a tradeoff from."""
    return [{k: np.mean([simulate(h, seed=s, **kw)[k] for s in range(seeds)]) for k in simulate(h, steps=10, **kw)}
            for h in half_spreads]


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    spreads = np.round(np.linspace(0.0, 0.40, 17), 3)
    res = sweep(spreads, skew=0.01)
    best = max(res, key=lambda r: r["pnl"])

    print(f"{'half-spread':>11}{'fills/step':>11}{'spread':>9}{'adverse':>9}{'inventory':>10}{'PnL/step':>10}")
    for r in res:
        print(f"{r['half_spread']:11.3f}{r['fill_rate']:11.3f}{r['spread']:9.4f}{r['adverse']:9.4f}"
              f"{r['inventory']:10.4f}{r['pnl']:10.4f}")
    print(f"\nbest half-spread: {best['half_spread']:.3f} (mid moves {VOL} per step)")

    print("\nInventory control at the best spread (12 independent runs each):")
    print(f"{'skew':>6}{'mean PnL/step':>15}{'worst run':>11}{'best run':>10}{'inventory std':>15}{'max |inv|':>11}")
    for skew in (0.0, 0.01, 0.03):
        runs = [simulate(best["half_spread"], skew=skew, seed=s) for s in range(12)]
        pnl = [r["pnl"] for r in runs]
        print(f"{skew:6.2f}{np.mean(pnl):15.4f}{min(pnl):11.4f}{max(pnl):10.4f}"
              f"{np.mean([r['inv_std'] for r in runs]):15.1f}{max(r['max_abs_inv'] for r in runs):11.0f}")

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    hs = [r["half_spread"] for r in res]
    a1.plot(hs, [r["fill_rate"] for r in res], "o-", color="#1f77b4")
    a1.set(title="Wider quotes, fewer fills", xlabel="Half-spread", ylabel="Fills per step")
    a1.grid(alpha=0.3)
    a2.plot(hs, [r["spread"] for r in res], "o-", color="#2ca02c", label="Spread captured")
    a2.plot(hs, [r["adverse"] for r in res], "o-", color="#d62728", label="Adverse selection")
    a2.plot(hs, [r["pnl"] for r in res], "o-", color="black", lw=2, label="Total PnL")
    a2.axhline(0, color="gray", lw=0.8)
    a2.axvline(best["half_spread"], color="gray", ls="--", lw=0.8)
    a2.annotate("best spread", (best["half_spread"], best["pnl"]), textcoords="offset points", xytext=(8, -18))
    a2.set(title="Where the money comes from (per step)", xlabel="Half-spread", ylabel="PnL per step")
    a2.legend(frameon=False)
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("spread_tradeoff.png", dpi=150)
