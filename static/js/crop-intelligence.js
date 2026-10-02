(() => {
  'use strict';
  const el=id=>document.getElementById(id);
  const money=v=>`₹${Number(v).toLocaleString('en-IN',{maximumFractionDigits:2})}`;
  let previewURL,decisionId,currentLots=[],busy=false;
  const seenAlerts=new Set();
  const token=document.querySelector('.intel').dataset.csrf;
  async function api(path,body) {
    const headers={'X-CSRF-Token':token};
    if(body && !(body instanceof FormData)) headers['Content-Type']='application/json';
    const response=await fetch(path,{method:body?'POST':'GET',headers,body:body instanceof FormData?body:body?JSON.stringify(body):undefined});
    let data;try {data=await response.json();} catch {throw new Error('Server returned an invalid response. Please try again.');}
    if(!response.ok) throw new Error(data.error||'Request failed');
    return data;
  }
  function error(message){el('intel-error').textContent=message;el('intel-error').hidden=false;}
  async function work(button,fn){
    if(busy)return;
    busy=true;el('intel-error').hidden=true;button.disabled=true;el('lot').disabled=true;
    const text=button.textContent;if(button.tagName==='BUTTON')button.textContent='Working…';
    try {await fn();} catch(e) {error(e.message);} finally {button.disabled=false;el('lot').disabled=false;button.textContent=text;busy=false;}
  }
  function lotId(){if(!el('lot').value)throw new Error('Select or create a crop lot first.');return Number(el('lot').value);}
  async function loadLots(selected){
    const data=await api('/crop-lots');currentLots=data.lots;
    el('lot').replaceChildren(new Option('Select a crop lot',''));
    currentLots.forEach(l=>el('lot').add(new Option(`${l.crop} · ${l.market} · ${l.variety} · ${l.grade}`,l.id)));
    if(selected){el('lot').value=selected;await loadLot();}
  }
  function historyRows(){
    return el('history').value.trim().split('\n').filter(Boolean).map(line=>{
      const parts=line.split(',');if(parts.length!==2 || !parts[0].trim() || !parts[1].trim() || !Number.isFinite(Number(parts[1])))throw new Error('Each history line must be YYYY-MM-DD,price.');
      return {date:parts[0].trim(),price:Number(parts[1])};
    });
  }
  function setPrices(data){
    el('history').value=data.prices.map(p=>`${p.date},${p.price}`).join('\n');
    if(data.current_price)el('price').value=data.current_price;
    el('price-status').textContent=`${data.prices.length} saved observations. ${data.needs_history?'Import earlier observations to reach at least 14.':'History ready.'}`;
  }
  function renderHealth(d){
    el('health-label').textContent=d.label;
    el('confidence').textContent=`Model confidence: ${(d.confidence*100).toFixed(1)}% · ${d.severity}`;
    el('review').textContent=d.storage_risk_inferred?'Severe disease: storage risk inferred. Immediate sale of marketable stock is recommended; separate spoiled produce.':d.needs_review?'Uncertain result: seek expert review before treating.':'Confirm diagnosis with a local agronomist.';
    ['organic','preventive'].forEach(k=>{el(k).replaceChildren();d.remedies[k].forEach(t=>{const li=document.createElement('li');li.textContent=t;el(k).append(li);});});
    el('chemical').textContent=d.remedies.dosage_status;el('chemical-doses').replaceChildren();
    d.remedies.chemical.forEach(r=>{const p=document.createElement('p');p.className='alert alert-light';p.textContent=`Extension reference: ${r.active_ingredient} ${r.formulation||'(formulation must be verified)'} — ${r.dose} ${r.unit}. ${r.method}. Source region: ${r.source_region}. Product-label verification required.`;el('chemical-doses').append(p);});
    el('localized-notice').textContent=d.remedies.localized?.notice||'';el('remedy-sources').replaceChildren();
    d.remedies.sources.forEach(url=>{const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Agricultural guidance source';a.className='d-block small';el('remedy-sources').append(a);});
    el('health').hidden=false;
  }
  async function loadLot(){
    el('health').hidden=true;el('decision').hidden=true;decisionId=null;el('leaf').value='';el('preview').hidden=true;el('compromised').checked=false;
    el('volume').value='';el('price').value='';el('history').value='';el('lot-history').replaceChildren();
    if(!el('lot').value)return;
    const id=lotId();const [history,prices]=await Promise.all([api(`/crop-lots/${id}/history`),api(`/market-prices?lot_id=${id}`)]);
    if(id!==Number(el('lot').value))return;
    setPrices(prices);
    if(history.position && history.position.remaining_quintals>0)el('volume').value=history.position.remaining_quintals;
    if(history.assessments.length)renderHealth(history.assessments[0].result);
    const items=[...history.assessments.map(a=>({date:a.created_at,text:`${a.label} · ${(a.confidence*100).toFixed(1)}% confidence`})),...history.decisions.map(d=>({date:d.created_at,text:`${d.result.action.replaceAll('_',' ')} · Sell ${d.result.sell_pct}% / Hold ${d.result.hold_pct}%`}))].sort((a,b)=>b.date.localeCompare(a.date));
    if(!items.length)el('lot-history').textContent='No assessments or decisions yet.';
    items.forEach(item=>{const p=document.createElement('p');p.textContent=`${item.date} UTC · ${item.text}`;el('lot-history').append(p);});
  }
  el('lot-form').addEventListener('submit',e=>{e.preventDefault();work(e.submitter,async()=>{
    const data={crop:el('new-crop').value,commodity:el('commodity').value,market:el('market').value,grade:el('grade').value,state:el('state').value,district:el('district').value,variety:el('variety').value,language:el('language').value};
    const d=await api('/crop-lots',data);await loadLots(d.id);
  });});
  el('lot').addEventListener('change',()=>{loadLot().catch(e=>error(e.message));});
  el('leaf').addEventListener('change',()=>{
    if(previewURL)URL.revokeObjectURL(previewURL);
    const file=el('leaf').files[0];if(file){previewURL=URL.createObjectURL(file);el('preview').src=previewURL;el('preview').hidden=false;}
  });
  el('image-form').addEventListener('submit',e=>{e.preventDefault();work(e.submitter,async()=>{
    el('health').hidden=true;el('decision').hidden=true;decisionId=null;
    const f=new FormData();f.append('lot_id',lotId());f.append('image',el('leaf').files[0]);f.append('storage_compromised',el('compromised').checked);
    renderHealth(await api('/predict-disease',f));await pollAlerts();
  });});
  el('risk').addEventListener('input',()=>el('risk-value').textContent=el('risk').value);
  el('price-source').addEventListener('change',()=>{
    const manual=el('price-source').value==='manual';el('price').required=manual;el('history').required=false;el('price').disabled=!manual;el('history').disabled=!manual;
  });
  el('history').required=false; // Urgent disease or stop-loss overrides do not require a forecast.
  el('sync-prices').addEventListener('click',()=>work(el('sync-prices'),async()=>setPrices(await api('/market-prices',{lot_id:lotId()}))));
  el('import-prices').addEventListener('click',()=>work(el('import-prices'),async()=>{
    const d=await api('/market-history',{lot_id:lotId(),history:historyRows()});el('price-status').textContent=`Saved ${d.imported} historical observations.`;
  }));
  el('upload-history').addEventListener('click',()=>work(el('upload-history'),async()=>{
    const file=el('csv-history').files[0];if(!file)throw new Error('Choose a CSV file.');
    const form=new FormData();form.append('lot_id',lotId());form.append('file',file);form.append('price_unit',el('csv-unit').value);form.append('source_label',el('csv-source').value);
    const d=await api('/market-history/import',form);setPrices(await api(`/market-prices?lot_id=${lotId()}`));el('price-status').textContent=`Saved ${d.imported} observations from ${d.source}.`;
  }));
  el('validate-forecast').addEventListener('click',()=>work(el('validate-forecast'),async()=>{
    const d=await api('/market-validation',{lot_id:lotId()});el('validation-output').textContent=`Held-out ${d.observations} observations (${d.from_date}–${d.to_date}): MAE ${money(d.mae)}/quintal, RMSE ${money(d.rmse)}, MAPE ${d.mape_pct}%. Unchanged-price baseline MAE ${money(d.baseline_mae)}. ${d.notice}`;
  }));
  function renderDecision(d){
    decisionId=d.id;el('action').textContent=d.disease_override?'SELL 100% IMMEDIATELY':d.action.replaceAll('_',' ');
    el('reason').textContent=d.reason;el('urgent').hidden=!d.urgent;el('sell-bar').style.width=d.sell_pct+'%';el('hold-bar').style.width=d.hold_pct+'%';el('gauge').setAttribute('aria-label',`Sell ${d.sell_pct}%, hold ${d.hold_pct}%`);
    el('sell-text').textContent=`Sell ${d.sell_pct}% · ${d.sell_quintals} quintals`;el('hold-text').textContent=`Hold ${d.hold_pct}% · ${d.hold_quintals} quintals`;
    el('cash-text').textContent=`Cash ${money(d.cash_raised)} · shortfall ${money(d.cash_shortfall)}`;
    el('volatility-text').textContent=d.volatility_index_pct===null?'Urgent action: forecast bypassed':`Daily volatility ${d.volatility_index_pct}% · price SD ${money(d.price_stddev)}`;
    el('stop-text').textContent=`Stop-loss trigger ${money(d.stop_loss_price)}/quintal · ${d.quote_date} · ${d.price_source}`;el('limitations').textContent=d.limitations;
    const c=el('forecast'),ctx=c.getContext('2d'),pts=d.forecast;ctx.clearRect(0,0,c.width,c.height);c.hidden=!pts.length;
    if(pts.length){
      const max=Math.max(...pts.map(p=>p.high)),min=Math.min(...pts.map(p=>p.low)),x=i=>20+i*(c.width-40)/Math.max(1,pts.length-1),y=p=>160-140*(p-min)/Math.max(max-min,1);
      ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.high)):ctx.moveTo(x(i),y(p.high)));[...pts].reverse().forEach((p,i)=>ctx.lineTo(x(pts.length-1-i),y(p.low)));ctx.closePath();ctx.fillStyle='#dbe9dd';ctx.fill();ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.expected)):ctx.moveTo(x(i),y(p.expected)));ctx.strokeStyle='#43855b';ctx.lineWidth=3;ctx.stroke();
      const last=pts[pts.length-1];el('range-text').textContent=`${last.date}: estimated ${money(last.low)}–${money(last.high)}/quintal. Prophet model interval; local accuracy needs validation.`;
    }else el('range-text').textContent='The urgent rule takes priority over price forecasts.';
    el('confirm').textContent='Confirm sale completed & save remaining holding';el('decision').hidden=false;
  }
  el('market-form').addEventListener('submit',e=>{e.preventDefault();work(e.submitter,async()=>{
    el('decision').hidden=true;decisionId=null;
    const source=el('price-source').value;
    const body={lot_id:lotId(),price_source:source,volume_quintals:Number(el('volume').value),cash_required:Number(el('cash').value),horizon_days:Number(el('horizon').value),stop_loss_pct:Number(el('stop').value),risk_aversion:Number(el('risk').value)};
    if(source==='manual'){body.current_price=Number(el('price').value);body.history=el('history').value.trim()?historyRows():[];}
    renderDecision(await api('/market-decision',body));await pollAlerts();
  });});
  el('confirm').addEventListener('click',()=>work(el('confirm'),async()=>{
    const d=await api('/holding-positions',{decision_id:decisionId});el('volume').value=d.remaining_quintals;decisionId=null;el('decision').hidden=true;await pollAlerts();
  }));
  async function pollAlerts(){
    const d=await api('/crop-alerts');el('alerts').replaceChildren();
    d.alerts.forEach(a=>{
      const box=document.createElement('div');box.className='alert alert-danger';const text=document.createElement('p');text.textContent=`${a.crop} · ${a.market}: ${a.message}`;box.append(text);
      const button=document.createElement('button');button.className='btn btn-sm btn-outline-danger';button.textContent='Acknowledge';button.addEventListener('click',()=>work(button,async()=>{await api(`/crop-alerts/${a.id}/acknowledge`,{});await pollAlerts();}));box.append(button);el('alerts').append(box);
      if(!seenAlerts.has(a.id) && 'Notification' in window && Notification.permission==='granted')new Notification(`${a.crop}: urgent crop alert`,{body:a.message,tag:`crop-alert-${a.id}`});seenAlerts.add(a.id);
    });
  }
  el('notify').addEventListener('click',async()=>{
    if(!('Notification' in window)){error('Browser notifications are unavailable; in-page alerts remain active.');return;}
    const permission=await Notification.requestPermission();el('notify').textContent=permission==='granted'?'Browser alerts enabled':'Browser alerts not enabled';
  });
  async function serviceStatus(){
    const d=await api('/intelligence-status');el('service-status').textContent=`Leaf analysis ${d.vision.ready?'ready':'unavailable'} · Price forecast ${d.prophet_ready?'ready':'unavailable'} · Live mandi feed ${d.live_feed_configured?'connected':'needs API key'} · Monitor ${d.monitor.status}`;
  }
  Promise.all([loadLots(),pollAlerts(),serviceStatus()]).catch(e=>error(e.message));
  setInterval(()=>{pollAlerts().catch(()=>{});serviceStatus().catch(()=>{});},30000);
})();
