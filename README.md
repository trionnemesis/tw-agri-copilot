# Taiwan Produce Watch

PR 1 provides a deterministic, static foundation for Taiwan wholesale produce market data. It persists normalized watchlist rows and source metadata, safely merges upstream corrections, and builds only from the requested saved ISO-date data. It does not provide seasonality, Buy Score recommendations, AI advice, traceability, or rolling analytics.

All displayed figures are **批發市場平均行情，非實際零售通路售價。**

## Local fixture build

```bash
PYTHONPATH=src python3 -m tpw validate-config
PYTHONPATH=src python3 -m tpw build --as-of 2026-08-25
PYTHONPATH=src python3 -m tpw verify-site
```

Required tests use committed fixtures; the live market adapter is intentionally excluded from CI.

`backfill --days N --end YYYY-MM-DD` uses bounded four-day fetch windows. It is a real live code path, but CI mocks it and no live 120-day pull is part of this repository checkout.

The Pages workflow is opt-in. It validates and deploys only after the repository variable `ENABLE_PAGES_DEPLOY` is explicitly set to `true`; repository creation alone does not publish the site.
