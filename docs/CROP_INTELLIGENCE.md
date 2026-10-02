# Crop health and selling intelligence

The new features extend the existing Flask, SQLite and Jinja/Bootstrap platform. The authenticated dashboard is `/crop-intelligence`, linked from AI Services. Both APIs are session-authenticated and protect writes with a CSRF token.

## Run

Use Python 3.11 (the supplied virtual environment uses 3.11):

```sh
venv/bin/pip install -r requirements.txt -r requirements-vision.txt
# Trained artifacts are already included; this command reinstalls the pinned model if needed.
venv/bin/python scripts/setup_vision.py
cp .env.example .env
# Add your own data.gov.in API key to AGMARKNET_API_KEY in .env for government quotes.
venv/bin/python app.py
```

Open `http://127.0.0.1:5001/crop-intelligence` and sign in using your platform account. Create a lot with exact government commodity, mandi, state, district, variety and grade names. The default trained leaf classifier supports tomato, potato and bell pepper. Other crops can still use the market engine.

The live-feed code is complete but a real data.gov.in API key was not supplied, so an authenticated live government request was not verified. Import a CSV with `date,price` columns or enter 14–365 recent dated observations to use the market engine immediately. Data.gov.in's selected resource supplies **current daily quotes**, not an arbitrary historical series: the database accumulates observations over time and import supplies the initial history. Never replace that missing history with invented prices. Empty or stale caches are explicitly reported.

## Architecture

Browser camera/upload + inputs → authenticated Flask blueprint → local MobileNetV3 / Prophet / allocation services → SQLite.

- `services/vision.py`: private CPU leaf inference, ordered class labels, checksum verification, preprocessing, confidence, review flags and disease-specific care.
- `services/forecasting.py`: Prophet on log prices, dated observations, current quote anchoring and 7–15 day model ranges. A bounded cache avoids refitting identical input series.
- `services/crop_engine.py`: volatility, cash-constrained mean–variance allocation and urgent-rule precedence.
- `services/market_feed.py`: bounded, timed requests to the official government resource; exact commodity/location/variety/grade matching; conflicting or ambiguous quotes rejected; daily observations stored with provenance.
- `services/monitor.py`: background price refresh and deduplicated alert creation for saved open holdings. It also responds to severe image assessments without requiring price history.
- `services/routes.py`: REST routes, validation, ownership, persistence, CSV-history JSON import, history and alert acknowledgement.
- `templates/crop_intelligence.html` and `static/js/crop-intelligence.js`: responsive camera/upload, remedy cards, price sources, CSV import, sell/hold gauge, chart, history and polling notifications.

## Override and allocation

A latest lot-specific severe assessment at confidence ≥0.90 triggers **SELL 100% IMMEDIATELY**, ahead of both a price forecast and cash optimization. The trained labels mark late blight as severe; confidence below the threshold flags review instead. This implements the requested precautionary policy. It **infers** shelf-life risk from disease; a leaf photo does not prove an entire harvested lot will rot. Sell marketable produce, segregate spoiled material, and confirm the diagnosis with an agronomist. Photos of harvested products are outside this leaf model's evaluated scope.

Only the latest assessment for the owned lot is used and it expires after 24 hours. Unrelated lots, other users' assessments and expired results cannot trigger the override. The client cannot supply disease severity or confidence to the market API. Severe disease and stop-loss decisions bypass historical-data and forecasting requirements.

For ordinary decisions, use up to 30 recent observations for volatility. Calendar gaps up to 7 days are retained rather than filled with fabricated prices. Daily variance uses log-return residuals normalized by the square root of the elapsed days. Return price SD in ₹/quintal and daily volatility as a percentage.

Fit Prophet to dated log prices; transform expected prices and its 95% model intervals back to ₹/quintal. These are model uncertainty intervals, **not locally calibrated guarantees**. Define:

```
mu = forecast_terminal_price / current_price - 1
variance = max(daily_volatility² × horizon,
               ((forecast_high - forecast_low)/(3.92 × current_price))²,
               1e-8)
optimal_hold = clip(mu / (risk_aversion × variance), 0, 1)
minimum_sell = min(1, cash_required/(current_price × volume))
sell_fraction = max(minimum_sell, 1 - optimal_hold)
```

This maximizes expected return minus a quadratic volatility penalty under the immediate-cash constraint. Sell percentage rounds upward. With 10 quintals at ₹5,000 and ₹20,000 cash needed, sale is **at least 40%**, and can increase when volatility dominates expected upside. Cash needs exceeding full-sale proceeds return an explicit shortfall. Fees, storage costs, spoilage discounts and physical minimum lot sizes are excluded.

## Holdings and monitoring

After the farmer confirms that the suggested sale actually happened, save remaining stock, original price and threshold (`original_price × (1 − risk_margin)`). Further checks compare with this stored threshold; they do not reset it to the latest quote. Confirmation is restricted to the latest decision, expires after one hour and is rejected if a newer severe assessment now prevents holding. Decisions recommend actions; no sale transactions are executed.

`python app.py` starts a monitor thread by default every 900 seconds (`CROP_MONITOR_INTERVAL_SECONDS`). SQLite leases avoid overlapping monitors. For a WSGI deployment, run a separate supervised worker:

```sh
venv/bin/python -m services.monitor --interval 900
# One-off check:
venv/bin/python -m services.monitor --once
```

The monitor polls AGMARKNET when configured, checks cached prices no older than three days, persists alerts and reports degraded status when fresh quotes are unavailable. This is periodic monitoring of daily reported mandi quotes, not a live tick-level execution service. Deduplication uses the holding generation and triggering disease assessment. In-app alerts are returned through `/crop-alerts`; the dashboard polls every 30 seconds. Optional browser notifications require explicit permission and an open dashboard. No SMS/email service is configured or implied. Acknowledgement records that the farmer saw the alert; it does not close the holding.

## API contracts

All POST endpoints require `X-CSRF-Token` from the dashboard. JSON errors distinguish authentication, CSRF, invalid input and unavailable integrations.

| Route | Purpose |
| --- | --- |
| `GET /crop-intelligence` | Dashboard |
| `GET/POST /crop-lots` | List/create owned lots |
| `POST /predict-disease` | Multipart `lot_id`, `image`, optional `storage_compromised` |
| `POST /market-decision` | Calculate and persist recommendation |
| `GET/POST /market-prices` | Cached prices / live feed refresh |
| `POST /market-history` | Validate and save dated price history |
| `POST /holding-positions` | Confirm latest decision and save remaining stock |
| `GET /crop-lots/<id>/history` | Owned assessments, decisions and saved holding |
| `GET /crop-alerts` | Unacknowledged alerts owned by current farmer |
| `POST /crop-alerts/<id>/acknowledge` | Acknowledge owned alert |
| `GET /intelligence-status` | Model, forecast, feed configuration and monitor status |

Lot creation:

```json
{"crop":"Tomato","market":"Official mandi name","state":"Tamil Nadu","district":"Official district name","variety":"Other","grade":"FAQ","language":"en"}
```

Market decision:

```json
{
  "lot_id": 1,
  "price_source": "manual",
  "current_price": 5000,
  "volume_quintals": 10,
  "cash_required": 20000,
  "horizon_days": 7,
  "stop_loss_pct": 10,
  "risk_aversion": 1,
  "history": [{"date":"YYYY-MM-DD","price":5000}]
}
```

Replace history with at least 14 valid recent observations. `price_source: "live"` fetches the current quote and accumulated cache; `"cache"` uses existing observations. These modes do not require `current_price` or `history` from the client. Submitted stock must equal saved remaining stock for an existing open holding. Use a new lot for new inventory.

## Database

`services/schema.sql` and additive migrations in `initialize()` run at startup:

- `crop_lots`: user, crop, mandi, grade, state, district, variety, official commodity name and language.
- `disease_assessments`: private image path, class, confidence, severity, storage risk, model version and complete result.
- `market_decisions`: linked lot and assessment, JSON input and result for audit.
- `holding_positions`: remaining stock, original price, stop-loss threshold and confirmed decision.
- `market_prices`: dated modal price and source, unique by lot/date.
- `crop_alerts`: decision-linked urgent audit records.
- `alert_events`: deduplicated background/in-app alerts and acknowledgement timestamps.
- `monitor_runs`, `monitor_leases`: worker status and coordination.

Foreign keys are enabled. Existing tables remain. Images are decoded, limited to 5 MB / 16 megapixels and saved under private `instance/crop_uploads` using randomized names without EXIF. The new session key is persisted privately or supplied with `SECRET_KEY`; it is no longer the original hardcoded placeholder. Back up the database before deployment. User-data retention and uploaded-file cleanup still need an operational policy.

## Model provenance and training

The included 6.3 MB artifact is an actually trained `mobilenet_v3_small`, not ImageNet-only or randomly initialized weights. Source: [imaflower/plantvillage-mobilenetv3](https://huggingface.co/imaflower/plantvillage-mobilenetv3), MIT license, pinned revision `d76fe187be1c4c3a5474f835a7a70cd08c7ab085`. Metadata includes source, architecture, checksum, ordered 15 classes and preprocessing. The source configuration specifies resize 256, center crop 224, RGB and ImageNet normalization. Its reported curated-dataset metrics are not independently verified field accuracy.

Inference returns confidence, top three classes, low-confidence review status and limitations. Unsupported crops, invalid/malformed images, very small images and nearly uniform images are rejected. These basic quality checks are **not a trained out-of-distribution detector**: arbitrary non-leaf images and unusual field conditions can still be misclassified, even confidently.

For an expanded local model:

```sh
venv/bin/python scripts/train_vision.py /path/to/grouped-dataset --epochs 10 --output models/custom-vision
# Set DISEASE_MODEL_PATH and DISEASE_LABELS_PATH to the exported artifacts in .env.
```

The script expects `train/`, `val/`, `test/` ImageFolder trees, matches class order, fine-tunes MobileNetV3, retains the best validation checkpoint, evaluates the held-out test set and exports a compatible artifact/report. Dataset splitting must group plant/source to avoid leakage. Commercial reliance requires field validation and confidence calibration. The training script is supplied; a new dataset-training run was not needed because the pinned trained artifact is included.

## Remedies and exact-dose references

`services/remedies.py` distinguishes healthy leaves, blights, bacterial symptoms, viruses and mites. It supplies organic/cultural steps, preventive care, sources and localized English/Hindi/Tamil treatment notices. Detailed treatment steps remain English. Viral disease does not receive a fictional chemical cure, and neem oil is not presented as a cure for late blight.

For tomato early/late blight, the catalog includes a sourced **Azoxystrobin 23% SC, 200 ml/acre** extension reference. For potato blights, an older source lists **Mancozeb 2 g/litre** without a formulation, which is explicitly marked incomplete. These reference amounts are not claimed to be universally safe or current legal product-label prescriptions. Current product registration, water volume, pre-harvest/re-entry intervals and suitability must be checked before application; those missing values are not invented. Sprays are for growing crops, not harvested produce. Other diseases return relevant nonchemical guidance and local expert review instead of fabricated doses.

References:

- [TNAU tomato early blight](https://agritech.tnau.ac.in/crop_protection/tomato_diseases_2.html).
- [TNAU tomato late blight](https://agritech.tnau.ac.in/crop_protection/tomato_diseases_8.html).
- [TNAU potato cultivation and disease management](https://agritech.tnau.ac.in/horticulture/horti_vegetables_potato.html).
- [Official current daily mandi-price resource](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi).
- [Prophet Python API](https://facebook.github.io/prophet/docs/quick_start.html).

## Verification

```sh
venv/bin/python -m unittest discover -s tests -v
node --check static/js/crop-intelligence.js
```

Tests cover real Prophet execution, real trained artifact loading, quality/unsupported-crop rejection, cash constraints, override before forecasting, saved stop-loss, history import/cache, strict provider market matching with mocked HTTP, background alerts/deduplication, ownership/acknowledgement, stale assessments, authentication, CSRF, upload errors and dashboard rendering. A real labeled PlantVillage late-blight photo was also run through inference, and lot creation was checked through the browser on an isolated test database. The browser file-chooser test was interrupted, so the camera/upload UI has not yet been fully verified on devices. Provider HTTP contract testing does not replace a real key-authenticated feed test.

Market commodity names are stored separately from the vision crop name so a bell pepper classifier can use the official mandi commodity `Capsicum`.
