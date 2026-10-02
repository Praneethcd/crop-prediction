"""Short-horizon Prophet forecasts with date gaps retained (no fabricated quotes)."""
from datetime import timedelta
from functools import lru_cache
from threading import Lock
import numpy as np

_LOCK = Lock()


@lru_cache(maxsize=64)
def _forecast(observations, current_price, today, horizon):
    import pandas as pd
    from prophet import Prophet
    frame = pd.DataFrame(observations, columns=['ds', 'y'])
    frame['ds'] = pd.to_datetime(frame['ds'])
    frame['y'] = np.log(frame['y'])
    # Explicit current quote anchors the model at the decision date.
    frame = frame[frame.ds.dt.date != today]
    frame = pd.concat([frame, pd.DataFrame({'ds':[pd.Timestamp(today)], 'y':[np.log(current_price)]})], ignore_index=True)
    model = Prophet(weekly_seasonality=len(frame) >= 28, yearly_seasonality=False,
                    daily_seasonality=False, interval_width=.95, uncertainty_samples=400,
                    changepoint_prior_scale=.05)
    # Prophet simulation consumes global RNG state; serialize for reproducibility.
    with _LOCK:
        rng_state = np.random.get_state()
        try:
            np.random.seed(42)
            model.fit(frame, seed=42)
            future = pd.DataFrame({'ds':[pd.Timestamp(today + timedelta(days=i)) for i in range(1,horizon+1)]})
            predicted = model.predict(future)
        finally:
            np.random.set_state(rng_state)
    result = []
    for row in predicted.itertuples():
        values = np.exp(np.clip([row.yhat, row.yhat_lower, row.yhat_upper], np.log(.01), np.log(1e12)))
        mid, low, high = map(float, values)
        if not np.isfinite(values).all():
            raise RuntimeError('Forecast produced non-finite prices')
        result.append({'date':row.ds.date().isoformat(), 'expected':round(mid,2),
                       'low':round(min(low,mid),2), 'high':round(max(high,mid),2)})
    return tuple(result)


def forecast_prices(dated, current_price, today, horizon):
    rows = tuple((d.isoformat(), p) for d,p in dated)
    return [dict(r) for r in _forecast(rows, float(current_price), today, int(horizon))]
