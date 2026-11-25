(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={observations:[],analysis:null,manifest:null,evidenceGraph:null,apiReady:false,spectral:null,spectralSourceRows:[],selectedSpectralCell:null,selectedObservationIndex:0};
const shortlistKey="chronosCandidateShortlist:v1";
const esc=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v,n=3)=>Number.isFinite(Number(v))?Number(v).toFixed(n):"n/a";
const pretty=x=>JSON.stringify(x,null,2);
function error(id,e){$(id).innerHTML='<div class="empty-state">'+esc(e.message||e)+'</div>';}
async function call(path,body){
 const r=await fetch("/api/v5"+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
 const p=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(typeof p.detail==="string"?p.detail:JSON.stringify(p.detail||"API request failed"));
 return p;
}
function needAPI(){if(!state.apiReady)throw new Error("Research API is not connected. Run python run.py from the repository root and open http://127.0.0.1:8000/causal-lab.html.");}
async function status(){
 try{const r=await fetch("/api/v5/status",{cache:"no-store"});if(!r.ok)throw Error();const x=await r.json();state.apiReady=true;
 $("api-mode").textContent="Research API connected · "+x.version+" · Physics";$("api-mode").classList.add("connected");$("run-status").textContent="API connected";}
 catch(_){state.apiReady=false;$("api-mode").textContent="Static website preview. Start the Python backend to run experiments."; $("api-mode").classList.remove("connected");$("run-status").textContent="Backend required for computation";}
}
function parse(id,label){try{return JSON.parse($(id).value);}catch(e){throw new Error(label+" JSON: "+e.message);}}
function pair(id,label){const a=$(id).value.split(",").map(Number);if(a.length!==2||a.some(x=>!Number.isFinite(x))||a[0]>=a[1])throw new Error(label+" needs two increasing values.");return a;}
function validObservationRows(){return state.observations.filter(row=>row.valid!==false);}
function updateRows(rows){
 state.observations=Array.isArray(rows)?rows:[];
 $("observations-json").value=pretty(state.observations);
 const ok=validObservationRows(),times=ok.map(row=>Number(row.mjd)).filter(Number.isFinite);
 $("data-class").textContent=ok.some(row=>String(row.calibration_group||"").startsWith("SYNTHETIC"))?"Synthetic fixture":"Supplied measurements";
 $("observation-count").textContent=ok.length;
 $("time-baseline").textContent=times.length?fmt(Math.max(...times)-Math.min(...times),1)+" d":"—";
 $("wave-count").textContent=new Set(ok.map(row=>row.wavelength_um)).size;
 const sharedId=new URLSearchParams(window.location.search).get("obs");
 const sharedIndex=sharedId?ok.findIndex(row=>String(row.observation_id??row.candidate_id??"")===sharedId):-1;
 if(sharedIndex>=0)state.selectedObservationIndex=sharedIndex;
 else if(state.selectedObservationIndex>=ok.length)state.selectedObservationIndex=Math.max(0,ok.length-1);
 track("sky-chart",ok,"sky");track("detector-chart",ok,"detector");
 drawTimeline(ok);renderSelectedObservation(ok);renderShortlist();
}
function track(id,rows,prefix){
 const canvas=$(id),g=canvas.getContext("2d"),w=canvas.width,h=canvas.height;
 g.clearRect(0,0,w,h);g.fillStyle="#091a25";g.fillRect(0,0,w,h);
 const pts=rows.map((row,index)=>({index,x:Number(row[prefix+"_x"]),y:Number(row[prefix+"_y"])}))
  .filter(point=>Number.isFinite(point.x)&&Number.isFinite(point.y));
 if(!pts.length){g.fillStyle="#91a8ab";g.font="11px sans-serif";g.fillText("No valid "+prefix+" coordinates supplied",18,28);return;}
 const xs=pts.map(point=>point.x),ys=pts.map(point=>point.y);
 const ax=Math.min(...xs),bx=Math.max(...xs),ay=Math.min(...ys),by=Math.max(...ys);
 const sx=Math.max(bx-ax,1e-8),sy=Math.max(by-ay,1e-8);
 const mapped=pts.map(point=>({...point,px:22+(point.x-ax)/sx*(w-42),py:h-22-(point.y-ay)/sy*(h-40)}));
 g.beginPath();mapped.forEach((point,i)=>i?g.lineTo(point.px,point.py):g.moveTo(point.px,point.py));
 g.strokeStyle=prefix==="sky"?"#8fe0cd":"#e7bd86";g.lineWidth=1.4;g.stroke();
 mapped.forEach(point=>{
  const selected=point.index===state.selectedObservationIndex;
  g.beginPath();g.arc(point.px,point.py,selected?7:3.3,0,Math.PI*2);
  g.fillStyle=prefix==="sky"?"#8fe0cd":"#e7bd86";g.fill();
  if(selected){g.beginPath();g.arc(point.px,point.py,10,0,Math.PI*2);g.strokeStyle="#f1d7a6";g.lineWidth=1.5;g.stroke();}
 });
}
function drawTimeline(rows){
 const canvas=$("observation-timeline"),g=canvas.getContext("2d"),w=canvas.width,h=canvas.height;
 g.clearRect(0,0,w,h);g.fillStyle="#081923";g.fillRect(0,0,w,h);
 if(!rows.length){g.fillStyle="#91a8ab";g.font="11px sans-serif";g.fillText("No valid observations to plot",18,34);return;}
 const times=rows.map(row=>Number(row.mjd)),lo=Math.min(...times),hi=Math.max(...times),span=Math.max(hi-lo,1e-9);
 const left=28,right=w-28,base=43;
 g.strokeStyle="rgba(143,224,205,.35)";g.lineWidth=1;g.beginPath();g.moveTo(left,base);g.lineTo(right,base);g.stroke();
 rows.forEach((row,index)=>{
  const x=left+(Number(row.mjd)-lo)/span*(right-left),selected=index===state.selectedObservationIndex;
  const synthetic=String(row.calibration_group||"").startsWith("SYNTHETIC");
  g.strokeStyle=selected?"#f1d7a6":synthetic?"#e7bd86":"#8fe0cd";
  g.lineWidth=selected?2:1;g.beginPath();g.moveTo(x,base-7);g.lineTo(x,base+7);g.stroke();
  g.beginPath();g.arc(x,base,selected?6:3.5,0,Math.PI*2);g.fillStyle=g.strokeStyle;g.fill();
  if(selected){g.fillStyle="#f1d7a6";g.font="10px sans-serif";g.fillText(String(row.observation_id??("row "+index)).slice(0,24),Math.min(Math.max(left,x-24),right-110),16);}
 });
 g.fillStyle="#728d93";g.font="9px sans-serif";g.fillText(fmt(lo,4)+" MJD",left,h-8);
 const rightLabel=fmt(hi,4)+" MJD";g.fillText(rightLabel,Math.max(left,right-g.measureText(rightLabel).width),h-8);
}
function renderSelectedObservation(rows){
 const panel=$("selected-observation-details");
 if(!rows.length){panel.innerHTML='<div class="empty-state">No valid observation is selected.</div>';return;}
 const index=Math.max(0,Math.min(state.selectedObservationIndex,rows.length-1)),row=rows[index];
 const cell=(label,value)=>'<div><small>'+esc(label)+'</small><b>'+esc(value??"n/a")+'</b></div>';
 panel.innerHTML=
  '<div class="selected-observation-heading"><b>Selected exposure '+(index+1)+' / '+rows.length+'</b><span>'+esc(row.observation_id??row.candidate_id??("input row "+index))+'</span></div>'+
  '<div class="selected-observation-grid">'+
  cell("Epoch MJD",fmt(row.mjd,5))+cell("Wavelength",fmt(row.wavelength_um,5)+" µm")+
  cell("Flux",fmt(row.flux,5))+cell("Uncertainty",fmt(row.sigma,5))+
  cell("Detector",row.detector_id)+cell("Calibration group",row.calibration_group)+
  cell("Sky position",fmt(row.sky_x,3)+", "+fmt(row.sky_y,3))+
  cell("Detector position",fmt(row.detector_x,3)+", "+fmt(row.detector_y,3))+
  '</div><p class="panel-note">The same exposure is highlighted in both coordinate plots and on the time axis. Coordinate values must remain traceable to the supplied measurement pipeline.</p>';
}
function selectObservation(index){
 const rows=validObservationRows();
 if(!rows.length)return;
 state.selectedObservationIndex=Math.max(0,Math.min(rows.length-1,index));
 drawTimeline(rows);track("sky-chart",rows,"sky");track("detector-chart",rows,"detector");renderSelectedObservation(rows);
}
function readShortlist(){
 try{const rows=JSON.parse(localStorage.getItem(shortlistKey)||"[]");return Array.isArray(rows)?rows:[];}
 catch(_){return [];}
}
function writeShortlist(rows){
 try{localStorage.setItem(shortlistKey,JSON.stringify(rows));}
 catch(_){$("shortlist-list").textContent="Local storage is unavailable in this browser.";}
}
function renderShortlist(){
 const panel=$("shortlist-list");
 if(!panel)return;
 const items=readShortlist();
 panel.innerHTML=items.length?items.map(item=>
  '<div class="shortlist-item"><button class="shortlist-select" type="button" data-shortlist-id="'+esc(item.observation_id)+'">'+esc(item.observation_id)+'</button><small>MJD '+fmt(item.mjd,4)+' · '+fmt(item.wavelength_um,4)+' µm · '+esc(item.detector_id||"detector n/a")+'</small><button class="shortlist-remove" type="button" data-remove-id="'+esc(item.observation_id)+'" aria-label="Remove '+esc(item.observation_id)+' from shortlist">×</button></div>'
 ).join(""):'<p class="panel-note">Your saved exposure shortlist is stored locally in this browser.</p>';
}
function saveSelectedObservation(){
 const rows=validObservationRows(),row=rows[state.selectedObservationIndex];
 if(!row){$("shortlist-status").textContent="No valid observation is selected.";return;}
 const id=String(row.observation_id??row.candidate_id??("row-"+state.selectedObservationIndex));
 const items=readShortlist();
 if(items.some(item=>String(item.observation_id)===id)){$("shortlist-status").textContent="This observation is already saved.";return;}
 items.push({observation_id:id,candidate_id:row.candidate_id??null,mjd:row.mjd,wavelength_um:row.wavelength_um,detector_id:row.detector_id,calibration_group:row.calibration_group});
 writeShortlist(items);renderShortlist();$("shortlist-status").textContent="Saved locally to shortlist.";
}
async function shareSelectedObservation(){
 const rows=validObservationRows(),row=rows[state.selectedObservationIndex];
 if(!row){$("shortlist-status").textContent="No valid observation is selected.";return;}
 const id=String(row.observation_id??row.candidate_id??"");
 if(!id){$("shortlist-status").textContent="This observation has no stable ID to share.";return;}
 const url=new URL(window.location.href);url.searchParams.set("obs",id);
 history.replaceState(null,"",url.toString());
 try{await navigator.clipboard.writeText(url.toString());$("shortlist-status").textContent="Share link copied. The link selects this observation when the same data set is loaded.";}
 catch(_){$("shortlist-status").textContent="Share URL updated in the address bar; clipboard permission was unavailable.";}
}
function downloadObservationCsv(){
 const rows=validObservationRows();if(!rows.length)return;
 const columns=[...new Set(rows.flatMap(row=>Object.keys(row)))];
 const quote=value=>'"'+String(typeof value==="object"?JSON.stringify(value):value??"").replace(/"/g,'""')+'"';
 const csv=[columns.map(quote).join(","),...rows.map(row=>columns.map(key=>quote(row[key])).join(","))].join("\n");
 const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
 const link=document.createElement("a");link.href=url;link.download="chronos-observations.csv";link.click();URL.revokeObjectURL(url);
}
function downloadCoordinatePlot(id,name){
 const canvas=$(id);if(!canvas)return;
 canvas.toBlob(blob=>{
  if(!blob)return;
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=name;link.click();URL.revokeObjectURL(url);
 },"image/png");
}
function heat(id,matrix,options={}){
 const c=$(id),g=c.getContext("2d"),h=matrix.length,w=matrix[0]?.length||0;
 g.clearRect(0,0,c.width,c.height);g.fillStyle="#071721";g.fillRect(0,0,c.width,c.height);
 const a=matrix.flat().map(Number).filter(Number.isFinite);
 if(!a.length||!w){g.fillStyle="#91a8ab";g.fillText("No supported measurements",18,30);return;}
 const lo=Math.min(...a),span=Math.max(Math.max(...a)-lo,1e-12),cw=c.width/w,ch=c.height/h;
 matrix.forEach((row,y)=>row.forEach((v,x)=>{
  const supported=options.valid?options.valid[y]?.[x]===true:Number.isFinite(Number(v));
  if(!supported||!Number.isFinite(Number(v))){
   g.fillStyle="#10232d";g.fillRect(x*cw,y*ch,cw+.4,ch+.4);
   g.save();g.beginPath();g.rect(x*cw,y*ch,cw,ch);g.clip();g.strokeStyle="rgba(137,164,169,.35)";g.lineWidth=1;
   for(let d=-ch;d<cw+ch;d+=7){g.beginPath();g.moveTo(x*cw+d,y*ch);g.lineTo(x*cw+d+ch,y*ch+ch);g.stroke();}
   g.restore();
  }else{
   const t=(v-lo)/span;g.fillStyle="hsl("+(196-48*t)+" 48% "+(22+44*t)+"%)";g.fillRect(x*cw,y*ch,cw+.4,ch+.4);
  }
 }));
 if(options.selected){
  const {timeIndex,wavelengthIndex}=options.selected;
  if(timeIndex>=0&&timeIndex<h&&wavelengthIndex>=0&&wavelengthIndex<w){
   g.strokeStyle="#f1d7a6";g.lineWidth=2;g.strokeRect(wavelengthIndex*cw+1,timeIndex*ch+1,Math.max(1,cw-2),Math.max(1,ch-2));
  }
 }
}
async function loadCase(){
 try{needAPI();const x=await call("/benchmark/synthetic-case",{scenario:$("scenario").value,seed:7,n_observations:14});updateRows(x.observations);state.analysis=null;
 $("verdict-box").innerHTML='<div class="result-symbol">✧</div><div><small>CONTROLLED SYNTHETIC CASE</small><h3>'+esc(x.scenario.replaceAll("_"," "))+'</h3><p>'+esc(x.warning)+'</p></div>';
 $("model-grid").innerHTML='<div class="empty-state">Run model comparison to inspect competing explanations.</div>'; $("run-status").textContent="Synthetic fixture loaded";}
 catch(e){error("model-grid",e);}
}
function renderAnalysis(x){
 state.analysis=x;const best=x.relative_model_support?.[0]||[];
 $("verdict-box").innerHTML='<div class="result-symbol">'+(x.verdict==="unknown"?"?":"◎")+'</div><div><small>'+(x.verdict==="unknown"?"EVIDENCE DOES NOT SEPARATE THE MODELS":"LEADING MODEL · NOT A DISCOVERY CLAIM")+'</small><h3>'+esc(x.verdict)+'</h3><p>Relative support '+fmt(best.relative_support)+'. ΔBIC to runner-up '+fmt(x.delta_bic_to_runner_up,2)+'.</p><p>'+esc((x.abstention_reasons||[]).join(" "))+'</p></div>';
 $("model-grid").innerHTML=(x.relative_model_support||[]).map(m=>'<article class="model-card"><div class="model-name">'+esc(m.name.replaceAll("_"," "))+'</div><div class="model-score">'+(100*m.relative_support).toFixed(1)+'%</div><div class="bar"><span style="width:'+(100*m.relative_support)+'%"></span></div><small>ΔBIC '+fmt(m.delta_bic,2)+'</small></article>').join("");
 $("causal-raw").hidden=false;$("causal-raw").textContent=pretty(x);track("sky-chart",state.observations,"sky");track("detector-chart",state.observations,"detector");
}
async function analyze(){
 try{needAPI();if(!state.observations.length)updateRows(parse("observations-json","Observations"));
 const x=await call("/causal/investigate",{observations:state.observations,min_relative_support:.65,min_delta_bic:6});renderAnalysis(x);$("run-status").textContent="Model comparison complete";}
 catch(e){error("model-grid",e);}
}
async function identifiability(){
 try{needAPI();const x=await call("/causal/identifiability",{observations:state.observations});
 $("identifiability-result").innerHTML='<div class="counter-row"><span>Identifiability</span><b>'+esc(x.status.replaceAll("_"," "))+'</b></div><div class="counter-row"><span>Design rank</span><b>'+x.rank+' / '+x.design_columns.length+'</b></div><div class="counter-row"><span>Condition number</span><b>'+fmt(x.condition_number,2)+'</b></div><p class="panel-note">'+esc((x.reasons||[]).join(" "))+'</p><p class="panel-note">'+esc((x.recommended_additional_measurements||[]).join(" "))+'</p>';}
 catch(e){error("identifiability-result",e);}
}
async function counterfactual(){
 try{needAPI();if(!state.analysis)await analyze();const x=await call("/causal/counterfactual",{observations:state.observations,intervention:$("intervention").value,amplitude:Number($("cf-amplitude").value),template_amplitude:Number($("cf-template").value),motion_x_per_day:.08,motion_y_per_day:-.04,seed:3});
 $("counterfactual-result").innerHTML='<div class="counter-row"><span>Original model</span><b>'+esc(state.analysis?.verdict||"not analysed")+'</b></div><div class="counter-row"><span>After intervention</span><b>'+esc(x.analysis.verdict)+'</b></div><div class="counter-row"><span>Intervention</span><b>'+esc(x.intervention)+'</b></div><div class="counter-row"><span>Original rows mutated</span><b>No</b></div><p class="panel-note">'+esc(x.warning)+'</p>';}
 catch(e){error("counterfactual-result",e);}
}
async function spectral(){
 try{
  needAPI();
  const rows=state.observations.filter(r=>r.valid!==false);
  if(rows.length<3)throw Error("Load observations first.");
  const w=rows.map(r=>Number(r.wavelength_um)),t=rows.map(r=>Number(r.mjd));
  if(w.some(v=>!Number.isFinite(v)||v<=0)||t.some(v=>!Number.isFinite(v)))throw Error("Observation wavelengths and epochs must be finite.");
  const a=Math.min(...w),b=Math.max(...w),timeMin=Math.min(...t),timeMax=Math.max(...t);
  if(!(b>a)||!(timeMax>timeMin))throw Error("Reconstruction needs a wavelength range and more than one epoch.");
  const groups=[...new Set(rows.map(r=>r.calibration_group))];
  if(groups.length!==1||!groups[0])throw Error("Use one calibration group per reconstruction.");
  const x=await call("/spectrotemporal/reconstruct",{
   samples:rows,
   wavelength_grid_um:Array.from({length:36},(_,i)=>a+(b-a)*i/35),
   time_grid_mjd:Array.from({length:20},(_,i)=>timeMin+(timeMax-timeMin)*i/19),
   wavelength_bandwidth_um:Number($("wave-bandwidth").value),
   time_bandwidth_days:Number($("time-bandwidth").value),
   min_neighbors:2,
   calibration_group:groups[0],
   shared_calibration_fractional_sigma:Number($("shared-calibration-fraction").value)
  });
  state.spectral=x;state.spectralSourceRows=rows;state.selectedSpectralCell=null;
  heat("spectral-heatmap",x.flux,{valid:x.valid});
  const count=x.valid.flat().filter(Boolean).length;
  $("spectrum-summary").textContent=count+" supported grid cells in calibration group "+groups[0]+". "+x.missing_data_policy;
  $("spectral-provenance").innerHTML='<div class="panel-note">Select any supported heatmap cell to inspect its source rows, generalized least-squares coefficients and separated uncertainty components. Diagonally hatched cells are unsupported.</div>';
 }catch(e){$("spectrum-summary").textContent=e.message||String(e);error("spectral-provenance",e);}
}
function inspectSpectralCell(event){
 const result=state.spectral,canvas=$("spectral-heatmap");
 if(!result||!canvas)return;
 const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)*canvas.width/rect.width,y=(event.clientY-rect.top)*canvas.height/rect.height;
 const nTime=result.time_mjd.length,nWave=result.wavelength_um.length;
 if(!nTime||!nWave)return;
 const timeIndex=Math.max(0,Math.min(nTime-1,Math.floor(y/(canvas.height/nTime))));
 const wavelengthIndex=Math.max(0,Math.min(nWave-1,Math.floor(x/(canvas.width/nWave))));
 state.selectedSpectralCell={timeIndex,wavelengthIndex};
 heat("spectral-heatmap",result.flux,{valid:result.valid,selected:state.selectedSpectralCell});
 const panel=$("spectral-provenance"),supported=result.valid?.[timeIndex]?.[wavelengthIndex]===true;
 const wave=result.wavelength_um[wavelengthIndex],mjd=result.time_mjd[timeIndex];
 if(!supported){
  panel.innerHTML='<div class="spectral-cell-heading"><b>Unsupported cell</b><span>MJD '+fmt(mjd,5)+' · '+fmt(wave,5)+' µm</span></div><p>This location has insufficient local temporal/spectral support. It remains missing; no measurement or extrapolated value is presented.</p><div class="counter-row"><span>Available neighbors</span><b>'+esc(result.n_samples?.[timeIndex]?.[wavelengthIndex]??0)+'</b></div>';
  return;
 }
 const get=key=>result[key]?.[timeIndex]?.[wavelengthIndex];
 const src=result.source_indices?.[timeIndex]?.[wavelengthIndex]||[];
 const weights=result.linear_weights?.[timeIndex]?.[wavelengthIndex]||[];
 const provenance=weights.map(row=>{
  const sourceIndex=Number(row.source_index);
  const source=state.spectralSourceRows.find((r,i)=>Number(r.source_index??i)===sourceIndex)||state.spectralSourceRows[sourceIndex];
  const id=source?.observation_id??("input row "+sourceIndex);
  return '<div class="spectral-source-row"><span>'+esc(id)+'<small>row '+sourceIndex+'</small></span><b>'+fmt(row.coefficient,5)+'</b></div>';
 }).join("");
 panel.innerHTML=
  '<div class="spectral-cell-heading"><b>Selected reconstruction cell</b><span>MJD '+fmt(mjd,5)+' · '+fmt(wave,5)+' µm</span></div>'+
  '<div class="spectral-cell-metrics">'+
   '<div><small>Flux estimate</small><b>'+fmt(get("flux"),5)+'</b></div>'+
   '<div><small>Measurement σ</small><b>'+fmt(get("sigma_measurement"),5)+'</b></div>'+
   '<div><small>Shared calibration σ</small><b>'+fmt(get("sigma_shared_calibration"),5)+'</b></div>'+
   '<div><small>Total σ</small><b>'+fmt(get("sigma_total"),5)+'</b></div>'+
   '<div><small>Samples</small><b>'+esc(get("n_samples"))+'</b></div>'+
   '<div><small>Effective N</small><b>'+fmt(get("effective_n"),3)+'</b></div>'+
  '</div>'+
  '<details open><summary>Source observations and GLS coefficients ('+src.length+')</summary>'+
  (provenance||'<p>No source-row coefficient record was returned.</p>')+
  '</details>'+
  '<p class="panel-note">These coefficients identify which supplied rows form this local estimate. Shared calibration uncertainty is an explicit group-level approximation; it is not independent noise per row.</p>';
}
async function featureEvolution(){
 try{
  needAPI();
  const epochs=parse("feature-epochs","Epoch spectra"),feature=pair("feature-interval","Feature interval"),blue=pair("feature-blue","Blue continuum"),red=pair("feature-red","Red continuum");
  const x=await call("/spectrotemporal/feature-evolution",{epochs,feature_interval_um:feature,continuum_intervals_um:[blue,red]});
  $("feature-evolution-result").innerHTML=x.epochs.map(r=>{
   const resolution=r.resolution_diagnostics||{},blend=r.blend_diagnostics||{};
   const lsf=resolution.lsf_fwhm_um==null?"not supplied":fmt(resolution.lsf_fwhm_um,5)+" µm";
   const sampling=resolution.samples_per_fwhm==null?"unknown":fmt(resolution.samples_per_fwhm,2)+" pixels/FWHM";
   return '<div class="counter-row"><span>'+esc(r.epoch_id)+' · MJD '+fmt(r.mjd,5)+'</span><b>EW '+fmt(r.equivalent_width_um,5)+' µm</b></div>'+
    '<div class="spectral-source-row"><span>Resolution · '+esc(lsf)+'<small>'+esc(sampling)+'</small></span><b>'+esc(resolution.sampling_status||"not assessed")+'</b></div>'+
    '<div class="spectral-source-row"><span>Blend screen</span><b>'+esc(blend.status||"not assessed")+'</b></div>';
  }).join("")+'<p class="panel-note">'+esc(x.warning)+' A possible-blend flag is a screening result, not molecular identification or deblending.</p>';
 }catch(e){error("feature-evolution-result",e);}
}
async function identity(){
 try{
  needAPI();
  const x=await call("/identity/associate",{
   candidate:parse("identity-candidate","Candidate"),
   catalogue_rows:parse("identity-catalogue","Catalogue"),
   search_radius_arcsec:10,
   background_density_per_arcsec2:.001,
   prior_match_probability:.9
  });
  const cards=x.matches.map(m=>{
   const motion=m.proper_motion_and_parallax||{},survey=m.survey_metadata||{};
   const baseline=motion.proper_motion_interval_years==null?"":fmt(motion.proper_motion_interval_years,2)+" yr epoch baseline";
   const correction=motion.parallax_applied?
    "Parallax correction: east "+fmt(motion.parallax_shift_east_mas,3)+" mas, north "+fmt(motion.parallax_shift_north_mas,3)+" mas; Earth baseline "+fmt(motion.parallax_baseline_au,3)+" AU":
    "No parallax correction applied";
   const uncertainty="Position σ "+fmt(m.combined_sigma_arcsec,3)+" arcsec; proper-motion σ "+fmt(m.proper_motion_sigma_arcsec,4)+" arcsec; parallax σ "+fmt(m.parallax_sigma_arcsec,4)+" arcsec";
   const surveyLine=[survey.survey,survey.bandpass,survey.wavelength_range_um,
    survey.angular_resolution_arcsec==null?null:fmt(survey.angular_resolution_arcsec,2)+" arcsec resolution"].filter(Boolean).join(" · ");
   const reference=typeof survey.reference_uri==="string"&&survey.reference_uri.startsWith("https://")?
    '<p><a href="'+esc(survey.reference_uri)+'" target="_blank" rel="noopener">Catalogue reference</a></p>':"";
   return '<article class="identity-match">'+
    '<div class="counter-row"><span>'+esc(m.source_id)+'<small>'+fmt(m.separation_arcsec,2)+' arcsec separation · likelihood ratio '+fmt(m.likelihood_ratio,3)+'</small></span><b>'+(100*m.association_probability).toFixed(1)+'%</b></div>'+
    '<p>'+esc(baseline)+'</p><p>'+esc(correction)+'</p><p>'+esc(uncertainty)+'</p>'+
    (surveyLine?'<small>'+esc(surveyLine)+'</small>':"")+reference+
    '</article>';
  }).join("");
  $("identity-result").innerHTML=
   '<div class="counter-row"><span>Association status</span><b>'+esc(x.status)+'</b></div>'+
   '<div class="counter-row"><span>No counterpart probability</span><b>'+fmt(x.no_counterpart_probability,4)+'</b></div>'+
   (cards||'<div class="empty-state">No catalogue source met the supplied search and likelihood criteria.</div>')+
   '<p class="panel-note">'+esc(x.assumptions.parallax_method||"Proper motion propagation only.")+'</p>'+
   '<p class="panel-note">'+esc(x.limitations.join(" "))+'</p>';
 }catch(e){error("identity-result",e);}
}
async function planner(){
 try{
  needAPI();
  const priorText=$("plan-alternative-priors").value.trim();
  const alternatives=priorText?parse("plan-alternative-priors","Alternative prior sets"):{};
  const x=await call("/observations/plan",{
   candidates:parse("plan-json","Observation forecasts"),
   measurement_sigma:Number($("plan-noise").value),
   alternative_priors:alternatives
  });
  const rows=x.ranked.map((m,i)=>{
   const feasibility=m.feasibility||{},verified=feasibility.status==="verified"&&feasibility.feasible===true;
   const source=verified?'<small>Verified by <a href="'+esc(feasibility.source_uri)+'" target="_blank" rel="noopener">external source</a> · checked '+esc(feasibility.checked_utc)+'</small>':'<small>Feasibility unverified · forecast ranking only</small>';
   const window=verified&&feasibility.window?'<small>Window '+esc(feasibility.window.start_utc)+' to '+esc(feasibility.window.end_utc)+'</small>':"";
   const measurement=m.measurement||{};
   const detail=[measurement.wavelength_um==null?null:fmt(measurement.wavelength_um,4)+" µm",measurement.detector_id,measurement.measurement_type].filter(Boolean).join(" · ");
   return '<article class="planner-candidate"><div class="counter-row"><span>'+(i+1)+'. '+esc(m.time||"Unnamed")+'</span><b>'+fmt(m.information_gain,3)+' bits</b></div>'+
    (detail?'<small>'+esc(detail)+'</small>':"")+'<small class="planner-feasibility">'+(verified?"FEASIBILITY VERIFIED":"FEASIBILITY NOT VERIFIED")+'</small>'+source+window+'</article>';
  }).join("");
  const sensitivity=Object.entries(x.prior_sensitivity||{}).map(([label,result])=>
   '<div class="counter-row"><span>'+esc(label)+'<small>Top-ranked: '+esc(result.top_ranked_time||"n/a")+'</small></span><b>'+result.ranked_candidates.length+' candidates</b></div>'
  ).join("");
  const rejected=(x.rejected||[]).map(row=>'<div class="spectral-source-row"><span>'+esc(row.time||"Unnamed candidate")+'<small>'+esc(row.reason||"Filtered by declared constraints")+'</small></span><b>Not ranked</b></div>').join("");
  $("plan-result").innerHTML='<div class="counter-row"><span>Recommendation status</span><b>'+esc(x.recommendation_status)+'</b></div>'+
   '<div class="planner-ranked-list">'+rows+'</div>'+
   (sensitivity?'<div class="planner-sensitivity"><b>Prior sensitivity</b>'+sensitivity+'</div>':"")+
   (rejected?'<div class="planner-sensitivity"><b>Excluded candidates</b>'+rejected+'</div>':"")+
   '<p class="panel-note">'+esc(x.limitations.join(" "))+'</p>';
 }catch(e){error("plan-result",e);}
}
async function detector(){
 try{needAPI();const psf=[[.003,.015,.025,.015,.003],[.015,.075,.11,.075,.015],[.025,.11,.24,.11,.025],[.015,.075,.11,.075,.015],[.003,.015,.025,.015,.003]];
 const x=await call("/detector/simulate",{shape:[40,40],sources:[{x:20.3,y:18.7,expected_electrons:Number($("detector-flux").value)}],psf_kernel:psf,background_electrons:Number($("detector-background").value),dark_current_electrons:1.5,read_noise_electrons:Number($("detector-read").value),hot_pixel_electrons:0,persistence_electrons:0,nonlinearity_per_electron:.00001,crosstalk_fraction:.005,crosstalk_axis:1,seed:9});
 heat("detector-heatmap",x.measured_electrons);$("detector-summary").textContent=x.noise_model;}
 catch(e){$("detector-summary").textContent=e.message||String(e);}
}
async function benchmark(){
 const kinds=["static_source","achromatic_variable","chromatic_variable","transient","moving_source","instrumental_artifact","mixed_sky_detector"],decisions=[];
 try{needAPI();$("run-benchmark").disabled=true;$("benchmark-status").textContent="Running cases…";
 for(let i=0;i<kinds.length;i++){const fixture=await call("/benchmark/synthetic-case",{scenario:kinds[i],seed:30+i,n_observations:14});let prediction="unknown";
 try{prediction=(await call("/causal/investigate",{observations:fixture.observations,min_relative_support:.55,min_delta_bic:4})).verdict;}catch(_){}
 decisions.push({truth:fixture.truth_label,prediction});$("benchmark-progress").style.width=((i+1)/kinds.length*100)+"%";$("benchmark-status").textContent="Completed "+(i+1)+" / "+kinds.length;}
 const s=await call("/benchmark/summary",{decisions});$("benchmark-result").innerHTML='<div class="metric"><small>CASES</small><b>'+s.n_total+'</b></div><div class="metric"><small>COVERAGE</small><b>'+(100*s.coverage).toFixed(1)+'%</b></div><div class="metric"><small>ACCURACY WHEN DECIDED</small><b>'+(s.accuracy_when_decided===null?"n/a":(100*s.accuracy_when_decided).toFixed(1)+"%")+'</b></div><div class="metric"><small>ABSTENTIONS</small><b>'+s.abstentions+'</b></div>';
 $("benchmark-table").innerHTML='<table><thead><tr><th>TRUTH</th><th>DECISION</th><th>RESULT</th></tr></thead><tbody>'+decisions.map(d=>'<tr><td>'+esc(d.truth)+'</td><td>'+esc(d.prediction)+'</td><td>'+(d.truth===d.prediction?"MATCH":"REVIEW")+'</td></tr>').join("")+'</tbody></table><p class="panel-note">'+esc(s.warning)+'</p>';$("benchmark-status").textContent="Synthetic software test only. Not real-data validation.";}
 catch(e){$("benchmark-status").textContent=e.message||String(e);}finally{$("run-benchmark").disabled=false;}
}
async function baselines(){
 try{needAPI();const thresholds=$("baseline-thresholds").value.split(",").map(Number);
 const x=await call("/benchmark/baselines",{truth_positions:parse("baseline-truth","Truth positions"),methods:parse("baseline-methods","Method detections"),score_thresholds:thresholds,match_radius:2,target_false_candidates_per_field:Number($("baseline-fpr").value)});
 $("baseline-result").innerHTML=Object.entries(x.matched_comparison).map(([name,m])=>'<div class="counter-row"><span>'+esc(name)+'</span><b>Completeness '+fmt(m.completeness)+' · FP '+fmt(m.false_candidates_per_field,2)+'</b></div>').join("")+'<p class="panel-note">'+esc(x.limitations.join(" "))+'</p>';}
 catch(e){error("baseline-result",e);}
}
async function population(){
 try{needAPI();const x=await call("/population/rate",{fields:parse("population-json","Field measurements"),minimum_completeness:.1,draws:10000,seed:4}),r=x.event_rate_per_sqdeg_day;
 $("population-result").innerHTML='<div class="counter-row"><span>Median rate</span><b>'+fmt(r.median,5)+'</b></div><div class="counter-row"><span>68% interval</span><b>'+fmt(r.lower_68,5)+' – '+fmt(r.upper_68,5)+'</b></div><div class="counter-row"><span>95% interval</span><b>'+fmt(r.lower_95,5)+' – '+fmt(r.upper_95,5)+'</b></div><div class="counter-row"><span>Included fields</span><b>'+x.field_count+'</b></div><div class="counter-row"><span>Skipped fields</span><b>'+x.skipped_fields.length+'</b></div>';}
 catch(e){error("population-result",e);}
}
async function manifest(){
 try{needAPI();const x=await call("/evidence/manifest",parse("manifest-json","Archive manifest"));const v=await call("/evidence/manifest/verify",{manifest:x});state.manifest=x;
 $("manifest-result").innerHTML='<div class="counter-row"><span>Manifest verification</span><b>'+(v.valid?"VALID":"INVALID")+'</b></div><div class="counter-row"><span>Input files</span><b>'+x.files.length+'</b></div><pre class="raw-output">'+esc(x.manifest_sha256)+'</pre><button class="button outline" id="download-manifest">Download JSON</button>';$("download-manifest").addEventListener("click",()=>download("chronos-manifest.json",x));}
 catch(e){error("manifest-result",e);}
}
async function evidenceGraph(){
 try{needAPI();if(!state.analysis)await analyze();if(!state.analysis)throw Error("Run model comparison first.");
 const x=await call("/evidence/graph",{candidate_id:state.observations[0].candidate_id||"candidate",observations:state.observations,analysis:state.analysis,manifest:state.manifest});
 state.evidenceGraph=x;
 $("evidence-graph-result").innerHTML='<div class="counter-row"><span>Evidence nodes</span><b>'+x.nodes.length+'</b></div><div class="counter-row"><span>Evidence links</span><b>'+x.edges.length+'</b></div><div class="counter-row"><span>Graph SHA-256</span><b>'+esc(x.graph_sha256.slice(0,18))+'…</b></div><button class="button outline" id="download-graph">Download graph JSON</button>';$("download-graph").addEventListener("click",()=>download("chronos-evidence-graph.json",x));}
 catch(e){error("evidence-graph-result",e);}
}
async function exportInvestigationPackage(){
 try{
  needAPI();
  if(!state.analysis)await analyze();
  if(!state.analysis)throw Error("A successful analysis response is required before export.");
  if(!state.manifest)throw Error("Create and verify an archive manifest first.");
  const command=$("reproduction-command").value.trim();
  if(!command)throw Error("Enter the exact reproduction command for this investigation.");
  const files=state.manifest.files||[];
  if(!files.length)throw Error("The manifest contains no source-product records.");
  const sourceFiles=files.map((f,i)=>({
   role:f.role||f.product_type||("source_"+(i+1)),
   archive_id:f.archive_id,
   product_type:f.product_type,
   release:f.release,
   detector:f.detector,
   native_uri:f.native_uri||f.uri,
   sha256:f.sha256,
   byte_count:f.bytes??f.byte_count,
   compatibility_group:f.compatibility_group||state.manifest.calibration_group,
   compatibility_status:f.compatibility_status
  }));
  for(const [i,f] of sourceFiles.entries()){
   if(!f.native_uri||!String(f.native_uri).startsWith("https://"))throw Error("Manifest source "+(i+1)+" needs its exact HTTPS native_uri.");
   if(!f.sha256||!f.archive_id||!f.product_type||!f.release||!f.detector)throw Error("Manifest source "+(i+1)+" is missing its archive ID, product family, release, detector or SHA-256.");
  }
  let graph=state.evidenceGraph;
  if(!graph){
   graph=await call("/evidence/graph",{
    candidate_id:state.observations[0]?.candidate_id||"candidate",
    observations:state.observations,
    analysis:state.analysis,
    manifest:state.manifest
   });
   state.evidenceGraph=graph;
  }
  const payload={
   candidate_id:state.analysis.candidate_id||state.observations[0]?.candidate_id||"candidate",
   analysis:state.analysis,
   evidence_graph:graph,
   source_files:sourceFiles,
   reproduction_command:command,
   code_commit:state.manifest.software?.pipeline_commit||state.manifest.software?.git_commit||null,
   environment:state.manifest.software||{},
   processing_configuration:state.manifest.processing_choices||{},
   failed_checks:(state.analysis.abstention_reasons||[]).map(reason=>({check:"analysis_abstention",status:"not_passed",reason}))
  };
  const response=await fetch("/api/v5/evidence/package/export",{
   method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)
  });
  if(!response.ok){
   const detail=await response.json().catch(()=>({}));
   throw Error(typeof detail.detail==="string"?detail.detail:JSON.stringify(detail.detail||"Package export failed"));
  }
  const blob=await response.blob();
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  const safe=String(payload.candidate_id).replace(/[^A-Za-z0-9_-]/g,"_").slice(0,64)||"candidate";
  link.href=url;link.download="chronos_"+safe+".zip";document.body.appendChild(link);link.click();link.remove();
  URL.revokeObjectURL(url);
  $("package-result").textContent="Investigation ZIP exported. This metadata-only package records exact source URIs and hashes; the original FITS bytes remain external.";
 }catch(e){error("package-result",e);}
}
function download(name,data){const u=URL.createObjectURL(new Blob([pretty(data)],{type:"application/json"})),a=document.createElement("a");a.href=u;a.download=name;a.click();URL.revokeObjectURL(u);}
function copySchema(){
 const schema={observation_id:"unique source observation ID",candidate_id:"candidate ID",mjd:"MJD",wavelength_um:"science wavelength from CWAVE/CBAND",flux:"measured source flux",sigma:"validated flux uncertainty",sky_x:"sky coordinate x",sky_y:"sky coordinate y",sky_sigma:"sky positional uncertainty",detector_x:"detector coordinate x from verified WCS A",detector_y:"detector coordinate y from verified WCS A",detector_sigma:"detector coordinate uncertainty",detector_id:"detector identifier",template_score:"calibrated detector-template score [0,1]",calibration_group:"verified compatible calibration group",valid:true};
 navigator.clipboard?.writeText(pretty(schema)).then(()=>$("run-status").textContent="Field schema copied",()=>{$("run-status").textContent="Clipboard unavailable";});
}
$("load-case").addEventListener("click",loadCase);$("analyze-case").addEventListener("click",analyze);
$("apply-json").addEventListener("click",()=>{try{updateRows(parse("observations-json","Observations"));}catch(e){error("model-grid",e);}});
$("copy-schema").addEventListener("click",copySchema);$("run-identifiability").addEventListener("click",identifiability);
$("run-counterfactual").addEventListener("click",counterfactual);$("reconstruct-spectrum").addEventListener("click",spectral);
$("measure-feature-evolution").addEventListener("click",featureEvolution);$("run-identity").addEventListener("click",identity);
$("spectral-heatmap").addEventListener("click",inspectSpectralCell);
$("observation-timeline").addEventListener("click",event=>{
 const canvas=$("observation-timeline"),rect=canvas.getBoundingClientRect(),rows=validObservationRows();
 if(!rows.length)return;
 const clickX=(event.clientX-rect.left)*canvas.width/rect.width,left=28,right=canvas.width-28;
 const times=rows.map(row=>Number(row.mjd)),lo=Math.min(...times),hi=Math.max(...times),span=Math.max(hi-lo,1e-9);
 const target=lo+Math.max(0,Math.min(1,(clickX-left)/(right-left)))*span;
 let nearest=0,distance=Infinity;times.forEach((time,index)=>{const d=Math.abs(time-target);if(d<distance){distance=d;nearest=index;}});
 selectObservation(nearest);
});
$("observation-timeline").addEventListener("keydown",event=>{
 if(event.key==="ArrowLeft"||event.key==="ArrowRight"){event.preventDefault();selectObservation(state.selectedObservationIndex+(event.key==="ArrowRight"?1:-1));}
});
$("save-selected-observation").addEventListener("click",saveSelectedObservation);
$("share-selected-observation").addEventListener("click",shareSelectedObservation);
$("export-observations-json").addEventListener("click",()=>download("chronos-observations.json",validObservationRows()));
$("export-observations-csv").addEventListener("click",downloadObservationCsv);
$("export-sky-plot").addEventListener("click",()=>downloadCoordinatePlot("sky-chart","chronos-sky-coordinates.png"));
$("export-detector-plot").addEventListener("click",()=>downloadCoordinatePlot("detector-chart","chronos-detector-coordinates.png"));
$("shortlist-list").addEventListener("click",event=>{
 const select=event.target.closest("[data-shortlist-id]"),remove=event.target.closest("[data-remove-id]"),items=readShortlist();
 if(select){const index=validObservationRows().findIndex(row=>String(row.observation_id??row.candidate_id??"")===select.dataset.shortlistId);if(index>=0)selectObservation(index);else $("shortlist-status").textContent="Saved item is not in the currently loaded observation set.";}
 if(remove){writeShortlist(items.filter(item=>String(item.observation_id)!==remove.dataset.removeId));renderShortlist();}
});
$("run-plan").addEventListener("click",planner);$("run-detector").addEventListener("click",detector);
$("run-benchmark").addEventListener("click",benchmark);$("run-baselines").addEventListener("click",baselines);
$("run-population").addEventListener("click",population);$("create-manifest").addEventListener("click",manifest);
$("create-evidence-graph").addEventListener("click",evidenceGraph);$("export-investigation-package").addEventListener("click",exportInvestigationPackage);status();
})();