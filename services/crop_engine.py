"""Cash-constrained portfolio allocation with disease and stop-loss precedence."""
import math
from datetime import datetime, date
from zoneinfo import ZoneInfo
import numpy as np
from services.forecasting import forecast_prices


def today_local():
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def number(value, name, minimum=0, maximum=1e12):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be numeric')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be numeric')
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return result


def validate_history(rows, today=None):
    today = today or today_local()
    if not isinstance(rows, list) or not 14 <= len(rows) <= 365:
        raise ValueError('Provide 14–365 observations for one crop, market, variety and grade; import history if the live feed cache is still warming up')
    if any(not isinstance(r,dict) or not isinstance(r.get('date'),str) for r in rows):
        raise ValueError('Each history observation needs an ISO date and price')
    dated = sorted((date.fromisoformat(r['date']),number(r['price'],'history price',.01)) for r in rows)
    gaps = [(b[0]-a[0]).days for a,b in zip(dated,dated[1:])]
    if min(gaps) <= 0 or max(gaps) > 7:
        raise ValueError('History must have unique dates and no gaps longer than 7 days')
    if not 0 <= (today-dated[-1][0]).days <= 3:
        raise ValueError('Latest price observation must be within the last three days')
    if (today-dated[0][0]).days > 730:
        raise ValueError('History cannot include observations older than two years')
    return dated


def decide(data, disease=None, position=None):
    price=number(data.get('current_price'),'current_price',.01)
    volume=number(data.get('volume_quintals'),'volume_quintals',.001,1e8)
    cash=number(data.get('cash_required',0),'cash_required')
    margin=number(data.get('stop_loss_pct',10),'stop_loss_pct',1,50)/100
    risk=number(data.get('risk_aversion',1),'risk_aversion',.1,10)
    horizon=number(data.get('horizon_days',7),'horizon_days',7,15)
    if horizon != int(horizon):raise ValueError('horizon_days must be an integer')
    reference=position['reference_price'] if position else price
    threshold=position['stop_loss_price'] if position else reference*(1-margin)
    reason=None
    disease_override=bool(disease and disease['severity']=='severe' and disease['confidence']>=.9)
    if disease_override:
        reason='DISEASE OVERRIDE: severe disease at ≥90% model confidence. SELL 100% IMMEDIATELY of marketable stock as a precaution; segregate spoiled produce. Shelf-life compromise is inferred, not measured.'
    elif position and price<=threshold:
        reason='STOP LOSS: price is at or below the saved risk threshold. Sell remaining marketable stock immediately.'
    # Urgent decisions must work even without enough history or an available forecaster.
    forecast=[];volatility=price_sd=None;model='risk override (forecast bypassed)'
    if reason:
        sell=1
    else:
        dated=validate_history(data.get('history'))
        recent=dated[-30:]
        prices=np.array([p for _,p in recent]);gaps=np.array([(b[0]-a[0]).days for a,b in zip(recent,recent[1:])])
        log_returns=np.diff(np.log(prices))
        drift=float(log_returns.sum()/gaps.sum())
        residuals=(log_returns-drift*gaps)/np.sqrt(gaps)
        volatility=float(np.std(residuals,ddof=1))
        price_sd=float(np.std(prices,ddof=1))
        forecast=forecast_prices(dated,price,today_local(),int(horizon))
        expected_return=forecast[-1]['expected']/price-1
        # Include forecast uncertainty as well as observed variance to reduce overconfidence.
        terminal_sigma=(forecast[-1]['high']-forecast[-1]['low'])/(3.92*price)
        variance=max(volatility**2*horizon,terminal_sigma**2,1e-8)
        optimal_hold=min(1,max(0,expected_return/(risk*variance)))
        sell=max(min(1,cash/(price*volume)),1-optimal_hold)
        reason='Cash-constrained mean–variance allocation using a Prophet forecast and recent market volatility.'
        model='Prophet log-price v1 · 95% model interval (not calibrated on this market)'
    pct=min(100,max(0,math.ceil(sell*100-1e-9)))
    return {'action':'SELL' if pct==100 else 'HOLD' if pct==0 else 'PARTIAL_SELL',
            'sell_pct':pct,'hold_pct':100-pct,'sell_quintals':round(volume*pct/100,6),
            'hold_quintals':round(volume*(100-pct)/100,6),'cash_raised':round(price*volume*pct/100,2),
            'cash_shortfall':round(max(0,cash-price*volume*pct/100),2),'reason':reason,
            'urgent':disease_override or bool(position and price<=threshold),'disease_override':disease_override,
            'volatility_index_pct':round(volatility*100,3) if volatility is not None else None,
            'price_stddev':round(price_sd,2) if price_sd is not None else None,
            'stop_loss_price':round(threshold,2),'reference_price':reference,'forecast':forecast,'model':model,
            'limitations':'Model intervals need market-specific validation. Fees, storage costs and quality discounts are excluded. Leaf disease does not prove harvested stock will rot.'}
