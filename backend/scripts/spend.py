"""Print total estimated model spend so far, per model and per provider."""
import _path  # noqa: F401

from climateguard.usage import totals

BUDGET = {"meta": 150.0, "baseten": 100.0}

rows = totals()
if not rows:
    print("No model calls logged yet.")
by_provider = {}
for (provider, model), t in sorted(rows.items()):
    by_provider[provider] = by_provider.get(provider, 0.0) + t['cost_usd']
    print(f"{provider:8} {model:36} calls={t['calls']:<5} cache_hits={t['cache_hits']:<5} "
          f"in={t['prompt_tokens']:<9} out={t['completion_tokens']:<9} ${t['cost_usd']:.6f}")
print()
for provider, budget in BUDGET.items():
    spent = by_provider.get(provider, 0.0)
    print(f"{provider:8} spent ${spent:.6f} of ${budget:.0f} credit ({spent / budget:.2%})")
