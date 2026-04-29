# Polymarket Builder Dashboard

Public analytics dashboard for a Polymarket builder using the V2 Data API.

## What It Shows

- Daily and weekly builder volume
- Daily and weekly active users
- Builder rank per returned period
- All-time bucket summary
- Auto-refresh every 5 minutes

The dashboard uses the public endpoint:

```text
https://data-api.polymarket.com/v1/builders/volume
```

It does not require private CLOB credentials.

## Environment

Set the builder display name exactly as Polymarket returns it:

```env
POLY_BUILDER_NAME=OpiPoliX
```

Optional override:

```env
POLYMARKET_DATA_API_HOST=https://data-api.polymarket.com
```

## Local Development

```bash
pip install -r requirements.txt
vercel dev
```

Open `http://localhost:3000`.

## Notes

The public Data API provides volume, active users, and rank buckets. It does not expose the old trade-level fields such as transaction hashes or exact trade counts. For those, the dashboard would need a separate authenticated V2 `/builder/trades` integration with `py-clob-client-v2`, L2 CLOB credentials, and `POLY_BUILDER_CODE`.
