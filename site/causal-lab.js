(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={observations:[],analysis:null,manifest:null,evidenceGraph:null,apiReady:false,spectral:null,spectralSourceRows:[],selectedSpectralCell:null,shortlist:[],coverageAudit:null,detectorOutput:null,plannerOutput:null,identityOutput:null};
const esc=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v,n=3)=>v===null||v===undefined||v===""||!Number.isFinite(Number(v))?"n/a":Number(v).toFixed(n);
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
function updateRows(rows){
 state.observations=rows;$("observations-json").value=pretty(rows);
 const ok=rows.filter(x=>x.valid!==false),times=ok.map(x=>Number(x.mjd));
 const classes=[...new Set(ok.map(x=>String(x.dataset_class||x.data_class||(x.synthetic_fixture===true?"synthetic":"unverified")).toLowerCase()))];
 $("data-class").textContent=classes.length===1?classes[0].toUpperCase():classes.length?"MIXED":"UNVERIFIED";
 $("data-class").dataset.class=classes.join(",");
 $("observation-count").textContent=ok.length;$("time-baseline").textContent=times.length?fmt(Math.max(...times)-Math.min(...times),1)+" d":"—";
 $("wave-count").textContent=new Set(ok.map(x=>x.wavelength_um)).size;
 track("sky-chart",ok,"sky");track("detector-chart",ok,"detector");
}
function drawAxes(canvas){
 const g=canvas.getContext("2d"),w=canvas.width,h=canvas.height;
 g.clearRect(0,0,w,h);g.fillStyle="#091a25";g.fillRect(0,0,w,h);g.strokeStyle="#29424e";
 for(let i=1;i<5;i++){g.beginPath();g.moveTo(18,i*h/5);g.lineTo(w-10,i*h/5);g.stroke();}
 return g;
}
function drawSeries(canvasId,points,label,seriesIndex=0){
 const c=$(canvasId),g=drawAxes(c),valid=points.filter(p=>Number.isFinite(p.x)&&p.y!==null&&Number.isFinite(p.y));
 if(!valid.length){g.fillStyle="#91a8ab";g.fillText("No supported values",12,24);return;}
 const xmin=Math.min(...valid.map(p=>p.x)),xmax=Math.max(...valid.map(p=>p.x));
 const ymin=Math.min(...valid.map(p=>p.y)),ymax=Math.max(...valid.map(p=>p.y)),span=Math.max(ymax-ymin,1e-12);
 const px=x=>24+(x-xmin)/Math.max(xmax-xmin,1e-12)*(c.width-42);
 const py=y=>c.height-18-(y-ymin)/span*(c.height-38);
 g.beginPath();valid.forEach((p,i)=>i?g.lineTo(px(p.x),py(p.y)):g.moveTo(px(p.x),py(p.y)));
 g.strokeStyle=["#8fe0cd","#e7bd86","#d8b6e8"][seriesIndex%3];g.lineWidth=2;g.stroke();
 valid.forEach(p=>{g.beginPath();g.arc(px(p.x),py(p.y),3,0,Math.PI*2);g.fillStyle=g.strokeStyle;g.fill();});
 g.fillStyle="#91a8ab";g.font="10px sans-serif";g.fillText(label||"",8,12);
}
function renderSpectralViews(result,ti,wi){
 drawSeries("epoch-spectrum",result.wavelength_um.map((x,i)=>({x,y:result.flux[ti][i]})),"MJD "+fmt(result.time_mjd[ti],5),0);
 drawSeries("spectral-lightcurve",result.time_mjd.map((x,i)=>({x,y:result.flux[i][wi]})),"λ "+fmt(result.wavelength_um[wi],5)+" µm",1);
 const c=$("spectral-uncertainty"),g=drawAxes(c),keys=["sigma_measurement","sigma_shared_calibration","sigma_total"];
 keys.forEach((key,index)=>{
  const arr=result[key]?.[ti]||[],finite=arr.filter(v=>v!==null&&Number.isFinite(Number(v))).map(Number);
  if(!finite.length)return;const top=Math.max(...keys.flatMap(k=>(result[k]?.[ti]||[]).filter(v=>v!==null&&Number.isFinite(Number(v))).map(Number)),1e-12);
  g.beginPath();let started=false;
  arr.forEach((v,i)=>{if(v===null||!Number.isFinite(Number(v)))return;const x=22+i*(c.width-42)/Math.max(1,arr.length-1),y=c.height-18-Number(v)/top*(c.height-38);if(!started){g.moveTo(x,y);started=true;}else g.lineTo(x,y);});
  g.strokeStyle=["#8fe0cd","#e7bd86","#d8b6e8"][index];g.setLineDash(index===1?[5,3]:[]);g.stroke();g.setLineDash([]);
  g.fillStyle=g.strokeStyle;g.fillText(["Statistical","Shared calibration","Total"][index],10+index*130,12);
 });
}
function renderTrajectoryBraid(rows){
 const c=$("trajectory-braid"),g=drawAxes(c),valid=rows.filter(r=>["sky_x","sky_y","detector_x","detector_y"].every(k=>r[k]!==null&&r[k]!==undefined&&Number.isFinite(Number(r[k]))));
 if(!valid.length){g.fillStyle="#91a8ab";g.fillText("Verified paired sky/detector coordinates not supplied",12,24);return;}
 const lane=(xk,yk,top,height,color,label)=>{
  const p=valid.map(r=>({x:Number(r[xk]),y:Number(r[yk])})),xmin=Math.min(...p.map(q=>q.x)),xmax=Math.max(...p.map(q=>q.x)),ymin=Math.min(...p.map(q=>q.y)),ymax=Math.max(...p.map(q=>q.y));
  const px=i=>24+i*(c.width-48)/Math.max(1,p.length-1),py=q=>top+height-8-(q.y-ymin)/Math.max(ymax-ymin,1e-9)*(height-20);
  g.beginPath();p.forEach((q,i)=>i?g.lineTo(px(i),py(q)):g.moveTo(px(i),py(q)));g.strokeStyle=color;g.stroke();
  p.forEach((q,i)=>{g.beginPath();g.arc(px(i),py(q),3,0,Math.PI*2);g.fillStyle=color;g.fill();});
  g.fillStyle=color;g.font="10px sans-serif";g.fillText(label,8,top+10);
  return p.map((q,i)=>({x:px(i),y:py(q)}));
 };
 const sky=lane("sky_x","sky_y",8,72,"#8fe0cd","Sky coordinates"),det=lane("detector_x","detector_y",98,72,"#e7bd86","Detector coordinates");
 sky.forEach((p,i)=>{g.beginPath();g.moveTo(p.x,p.y+4);g.lineTo(det[i].x,det[i].y-4);g.strokeStyle="#8ea9a8";g.globalAlpha=.25;g.stroke();g.globalAlpha=1;});
 g.fillStyle="#91a8ab";g.font="9px sans-serif";g.fillText("Links pair exposure indices; they are not a WCS transform.",8,c.height-5);
}
function renderObservationTimeline(rows){
 const c=$("observation-timeline"),g=drawAxes(c),times=rows.map(r=>Number(r.mjd)).filter(Number.isFinite);
 if(!times.length){g.fillStyle="#91a8ab";g.fillText("No valid observation timestamps",12,24);return;}
 const lo=Math.min(...times),hi=Math.max(...times),span=Math.max(hi-lo,1e-9),y=c.height/2;
 rows.forEach((r,i)=>{const t=Number(r.mjd);if(!Number.isFinite(t))return;const x=24+(t-lo)/span*(c.width-48);
  g.beginPath();g.arc(x,y+(i%2?14:-14),5,0,Math.PI*2);
  const cls=String(r.dataset_class||r.data_class||(r.synthetic_fixture===true?"synthetic":"unverified"));
  g.fillStyle=r.valid===false?"#b56f5e":cls==="real"?"#8fe0cd":cls==="synthetic"?"#e7bd86":"#96bce0";g.fill();
 });
 c._rows=rows;c.title="Select an observation. Dot colour is inherited data class: real, synthetic or unverified.";
}
function selectExposure(event){
 const c=$("observation-timeline"),rows=c._rows||[];if(!rows.length)return;
 const rect=c.getBoundingClientRect(),px=((event.offsetX??event.clientX-rect.left)/Math.max(rect.width,1))*c.width;
 const valid=rows.map((r,i)=>({r,i,t:Number(r.mjd)})).filter(x=>Number.isFinite(x.t));
 if(!valid.length)return;const lo=Math.min(...valid.map(x=>x.t)),hi=Math.max(...valid.map(x=>x.t)),target=lo+(px/c.width)*(hi-lo);
 const chosen=valid.reduce((best,x)=>Math.abs(x.t-target)<Math.abs(best.t-target)?x:best);
 const r=chosen.r; $("selected-exposure").textContent="Selected "+(r.observation_id||r.measurement_id||chosen.i)+" · MJD "+fmt(r.mjd,5)+" · "+fmt(r.wavelength_um,5)+" µm · "+(r.dataset_class||r.data_class||(r.synthetic_fixture===true?"synthetic":"unverified"))+" · "+(r.calibration_group||"no calibration group");
}
function renderIdentityNetwork(result){
 const c=$("identity-network"),g=drawAxes(c),matches=(result.matches||[]).slice(0,7),cx=42,cy=c.height/2;
 matches.forEach((m,i)=>{const x=c.width-88,y=20+i*(c.height-56)/Math.max(1,matches.length-1);
  g.beginPath();g.moveTo(cx,cy);g.lineTo(x,y);g.strokeStyle="#8fe0cd";g.globalAlpha=Math.max(.12,Math.min(1,m.association_probability));g.stroke();g.globalAlpha=1;
  g.beginPath();g.arc(x,y,5,0,Math.PI*2);g.fillStyle="#e7bd86";g.fill();g.fillStyle="#c9d8d6";g.font="10px sans-serif";g.fillText(String(m.source_id).slice(0,14)+" "+(100*m.association_probability).toFixed(1)+"%",x-72,y-8);
 });
 const p=Number(result.no_counterpart_probability||0),x=c.width-82,y=c.height-20;g.beginPath();g.moveTo(cx,cy);g.lineTo(x,y);g.setLineDash([4,3]);g.strokeStyle="#d5a2a2";g.stroke();g.setLineDash([]);g.beginPath();g.arc(x,y,5,0,Math.PI*2);g.fillStyle="#d5a2a2";g.fill();g.fillStyle="#d5a2a2";g.font="9px sans-serif";g.fillText("No match "+(100*p).toFixed(1)+"%",x-72,y-9);
 g.beginPath();g.arc(cx,cy,8,0,Math.PI*2);g.fillStyle="#8fe0cd";g.fill();
}
function renderInformationGain(result){
 const c=$("information-gain-landscape"),g=drawAxes(c),items=result.science_only_ranked||[];
 if(!items.length){g.fillStyle="#91a8ab";g.fillText("No forecasts",12,24);return;}
 const max=Math.max(...items.map(x=>x.information_gain_bits),1e-12),step=(c.height-26)/items.length;
 items.forEach((item,i)=>{const y=10+i*step,bar=(c.width-160)*item.information_gain_bits/max;
  g.fillStyle="#8fe0cd";g.fillRect(125,y,bar,Math.max(5,step-4));g.fillStyle="#c9d8d6";g.font="10px sans-serif";g.fillText(String(item.candidate_observation_id).slice(0,17),5,y+10);g.fillText(item.information_gain_bits.toFixed(3)+" bits",128+bar,y+10);});
}
function renderEvidenceGraph(graph){
 const c=$("evidence-lineage"),g=drawAxes(c),nodes=graph.nodes||[],edges=graph.edges||[];
 if(!nodes.length){g.fillStyle="#91a8ab";g.fillText("Evidence graph not built",12,24);return;}
 const pos=new Map();nodes.forEach((n,i)=>pos.set(n.id,{x:24+(i%6)*(c.width-48)/5,y:20+Math.floor(i/6)*(c.height-40)/Math.max(1,Math.ceil(nodes.length/6)-1)}));
 edges.forEach(e=>{const a=pos.get(e.source),b=pos.get(e.target);if(!a||!b)return;g.beginPath();g.moveTo(a.x,a.y);g.lineTo(b.x,b.y);g.strokeStyle="#6f9d9d";g.stroke();});
 nodes.forEach(n=>{const p=pos.get(n.id);g.beginPath();g.arc(p.x,p.y,4,0,Math.PI*2);g.fillStyle=n.type==="candidate"?"#e7bd86":"#8fe0cd";g.fill();});
}
function exportJSON(name,data){
 const blob=new Blob([pretty(data)],{type:"application/json"}),url=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function loadShortlist(){
 try{state.shortlist=[...new Set(JSON.parse(localStorage.getItem("chronosCandidateShortlist")||"[]").map(String))];}catch(_){state.shortlist=[];}
 const params=new URLSearchParams(location.hash.slice(1)),shared=params.get("shortlist");if(shared)state.shortlist=[...new Set(shared.split(",").filter(Boolean))];
 renderShortlist();
}
function saveShortlist(){
 try{localStorage.setItem("chronosCandidateShortlist",JSON.stringify(state.shortlist));}catch(_){}
 renderShortlist();
}
function renderShortlist(){
 if(!$("shortlist-count"))return;
 $("shortlist-count").textContent=state.shortlist.length+" candidates";
 $("shortlist-results").innerHTML=state.shortlist.map(id=>'<div class="counter-row"><span>'+esc(id)+'</span><button class="button text-button" data-remove-shortlist="'+esc(id)+'">Remove</button></div>').join("")||'<div class="empty-state">No candidates saved.</div>';
 $("shortlist-results").querySelectorAll("[data-remove-shortlist]").forEach(b=>b.addEventListener("click",()=>{state.shortlist=state.shortlist.filter(x=>x!==b.dataset.removeShortlist);saveShortlist();}));
 ["compare-a","compare-b"].forEach((id,i)=>{const el=$(id),old=el.value;el.innerHTML='<option value="">'+(i?"Second":"First")+' candidate</option>';state.shortlist.forEach(v=>{const op=document.createElement("option");op.value=v;op.textContent=v;el.append(op);});if(state.shortlist.includes(old))el.value=old;});
}
function track(id,rows,prefix){
 const c=$(id),g=c.getContext("2d"),w=c.width,h=c.height;g.clearRect(0,0,w,h);g.fillStyle="#091a25";g.fillRect(0,0,w,h);if(!rows.length)return;
 const xs=rows.map(r=>Number(r[prefix+"_x"])),ys=rows.map(r=>Number(r[prefix+"_y"]));
 const ax=Math.min(...xs),bx=Math.max(...xs),ay=Math.min(...ys),by=Math.max(...ys);
 const sx=Math.max(bx-ax,1e-8),sy=Math.max(by-ay,1e-8);
 const pts=rows.map(r=>({x:22+(r[prefix+"_x"]-ax)/sx*(w-42),y:h-22-(r[prefix+"_y"]-ay)/sy*(h-40)}));
 g.beginPath();pts.forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.strokeStyle=prefix==="sky"?"#8fe0cd":"#e7bd86";g.stroke();
 pts.forEach(p=>{g.beginPath();g.arc(p.x,p.y,3.3,0,Math.PI*2);g.fillStyle=prefix==="sky"?"#8fe0cd":"#e7bd86";g.fill();});
}
function heat(id,matrix,options={}){
 const c=$(id),g=c.getContext("2d"),h=matrix.length,w=matrix[0]?.length||0;
 g.clearRect(0,0,c.width,c.height);g.fillStyle="#071721";g.fillRect(0,0,c.width,c.height);
 const a=matrix.flat().filter(v=>v!==null&&v!==undefined).map(Number).filter(Number.isFinite);
 if(!a.length||!w){g.fillStyle="#91a8ab";g.fillText("No supported measurements",18,30);return;}
 const lo=Math.min(...a),span=Math.max(Math.max(...a)-lo,1e-12),cw=c.width/w,ch=c.height/h;
 matrix.forEach((row,y)=>row.forEach((v,x)=>{
  const supported=options.valid?options.valid[y]?.[x]===true:(v!==null&&v!==undefined&&Number.isFinite(Number(v)));
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
  const allRows=state.observations;
  const valid=allRows.filter(r=>r.valid!==false);
  if(valid.length<3)throw Error("Load at least three valid source-specific measurements.");
  const w=valid.map(r=>Number(r.wavelength_um)),t=valid.map(r=>Number(r.mjd));
  if(w.some(v=>!Number.isFinite(v)||v<=0)||t.some(v=>!Number.isFinite(v)))throw Error("Wavelengths and timestamps must be finite.");
  const groups=[...new Set(valid.map(r=>r.calibration_group))];
  if(groups.length!==1||!groups[0])throw Error("Reconstruct one explicitly compatible calibration group at a time.");
  const waveMin=Math.min(...w),waveMax=Math.max(...w),timeMin=Math.min(...t),timeMax=Math.max(...t);
  if(!(waveMax>waveMin)||!(timeMax>timeMin))throw Error("Reconstruction requires a sampled wavelength range and more than one epoch.");
  const covariance=$("measurement-covariance").value.trim()?parse("measurement-covariance","Observation covariance"):null;
  const x=await call("/spectrotemporal/reconstruct",{
   samples:allRows,
   wavelength_grid_um:Array.from({length:36},(_,i)=>waveMin+(waveMax-waveMin)*i/35),
   time_grid_mjd:Array.from({length:20},(_,i)=>timeMin+(timeMax-timeMin)*i/19),
   wavelength_bandwidth_um:Number($("wave-bandwidth").value),
   time_bandwidth_days:Number($("time-bandwidth").value),
   min_neighbors:2,
   calibration_group:groups[0],
   shared_calibration_fractional_sigma:Number($("shared-calibration-fraction").value),
   measurement_covariance:covariance,
   include_grid_covariance:$("include-grid-covariance").checked
  });
  state.spectral=x;state.spectralSourceRows=allRows;state.selectedSpectralCell=null;
  heat("spectral-heatmap",x.flux,{valid:x.valid});
  const count=x.valid.flat().filter(Boolean).length;
  $("spectrum-summary").textContent=count+" supported cells · "+(x.data_class||"unverified")+" · group "+groups[0]+". "+x.missing_data_policy;
  $("spectral-provenance").innerHTML='<div class="panel-note">Select a grid cell to inspect source rows, GLS coefficients and statistical/shared-calibration uncertainty. Hatching marks unsupported cells. Native sampled wavelengths: '+(x.native_wavelength_samples_um||[]).length+'; native epochs: '+(x.native_observation_times_mjd||[]).length+'.</div>';
  drawSeries("epoch-spectrum",x.wavelength_um.map((v,i)=>({x:v,y:x.flux[0][i]})),"Earliest supported epoch");
  exportJSON("chronos-spectrotemporal-reconstruction.json",x);
 }catch(e){$("spectrum-summary").textContent=e.message||String(e);error("spectral-provenance",e);}
}

function showSpectralCell(timeIndex,wavelengthIndex){
 const result=state.spectral;if(!result)return;
 const nTime=result.time_mjd.length,nWave=result.wavelength_um.length;
 timeIndex=Math.max(0,Math.min(nTime-1,timeIndex));wavelengthIndex=Math.max(0,Math.min(nWave-1,wavelengthIndex));
 state.selectedSpectralCell={timeIndex,wavelengthIndex};
 heat("spectral-heatmap",result.flux,{valid:result.valid,selected:state.selectedSpectralCell});
 renderSpectralViews(result,timeIndex,wavelengthIndex);
 const panel=$("spectral-provenance"),supported=result.valid?.[timeIndex]?.[wavelengthIndex]===true;
 const wave=result.wavelength_um[wavelengthIndex],mjd=result.time_mjd[timeIndex];
 if(!supported){
  panel.innerHTML='<div class="spectral-cell-heading"><b>Unsupported region</b><span>MJD '+fmt(mjd,5)+' · '+fmt(wave,5)+' µm</span></div><p>Insufficient local support. This remains missing; no measured value or extrapolation is presented.</p>';
  return;
 }
 const sources=result.linear_weights?.[timeIndex]?.[wavelengthIndex]||[];
 const provenance=sources.map(row=>{
  const index=Number(row.input_index??row.source_index);
  const source=state.spectralSourceRows[index]||{};
  const observation=source.observation_id||source.measurement_id||("input row "+index);
  return '<div class="spectral-source-row"><span>'+esc(observation)+'<small>source row '+esc(row.source_index)+'</small></span><b>'+fmt(row.coefficient,5)+'</b></div>';
 }).join("");
 const get=key=>result[key]?.[timeIndex]?.[wavelengthIndex];
 panel.innerHTML=
  '<div class="spectral-cell-heading"><b>'+esc(result.cell_class?.[timeIndex]?.[wavelengthIndex]||"inferred")+'</b><span>MJD '+fmt(mjd,5)+' · '+fmt(wave,5)+' µm</span></div>'+
  '<div class="spectral-cell-metrics">'+
   '<div><small>Flux</small><b>'+fmt(get("flux"),5)+'</b></div>'+
   '<div><small>Statistical σ</small><b>'+fmt(get("sigma_measurement"),5)+'</b></div>'+
   '<div><small>Shared calibration σ</small><b>'+fmt(get("sigma_shared_calibration"),5)+'</b></div>'+
   '<div><small>Total σ</small><b>'+fmt(get("sigma_total"),5)+'</b></div>'+
   '<div><small>Neighbors</small><b>'+esc(get("n_samples"))+'</b></div>'+
   '<div><small>Effective N</small><b>'+fmt(get("effective_n"),3)+'</b></div>'+
  '</div><details open><summary>Contributing input rows ('+sources.length+')</summary>'+(provenance||"<p>No row-level weights returned.</p>")+'</details>'+
  '<p class="panel-note">An inferred cell is a model-based local estimate, not an additional measurement. The full source rows are retained in the response.</p>';
}
function inspectSpectralCell(event){
 const result=state.spectral,canvas=$("spectral-heatmap");if(!result||!canvas)return;
 if(event.key){
  const current=state.selectedSpectralCell||{timeIndex:0,wavelengthIndex:0};
  let t=current.timeIndex,w=current.wavelengthIndex;
  if(event.key==="ArrowLeft")w--;else if(event.key==="ArrowRight")w++;
  else if(event.key==="ArrowUp")t--;else if(event.key==="ArrowDown")t++;
  else if(event.key!=="Enter"&&event.key!==" "){return;}
  event.preventDefault();showSpectralCell(t,w);return;
 }
 const rect=canvas.getBoundingClientRect();
 const px=((event.offsetX??event.clientX-rect.left)/Math.max(rect.width,1))*canvas.width;
 const py=((event.offsetY??event.clientY-rect.top)/Math.max(rect.height,1))*canvas.height;
 const t=Math.floor(py/(canvas.height/result.time_mjd.length));
 const w=Math.floor(px/(canvas.width/result.wavelength_um.length));
 showSpectralCell(t,w);
}

async function featureEvolution(){
 try{
  needAPI();
  const epochs=parse("feature-epochs","Epoch spectra"),feature=pair("feature-interval","Feature interval");
  const blue=pair("feature-blue","Blue continuum"),red=pair("feature-red","Red continuum");
  const blends=parse("feature-blends","Potential blend intervals");
  const labs=parse("feature-lab-references","Laboratory reference spectra");
  const x=await call("/spectrotemporal/feature-evolution",{
   epochs,feature_interval_um:feature,continuum_intervals_um:[blue,red],
   potential_blend_intervals_um:blends,
   spectral_resolution_R:$("feature-resolution").value?Number($("feature-resolution").value):null,
   lsf_fwhm_um:$("feature-lsf").value?Number($("feature-lsf").value):null,
   continuum_model:$("feature-continuum-model").value,
   laboratory_references:labs
  });
  $("feature-evolution-result").innerHTML=x.epochs.map(row=>{
   const resolution=row.resolution_diagnostics||{},blend=row.blend_diagnostics||{};
   const labs=(row.laboratory_reference_comparisons||[]).map(result=>'<div class="spectral-source-row"><span>'+esc(result.reference_id)+'<small>'+esc(result.status)+'</small></span><b>RMS '+fmt(result.normalized_shape_rms,4)+'</b></div>').join("");
   return '<div class="counter-row"><span>'+esc(row.epoch_id)+' · MJD '+fmt(row.mjd,5)+'</span><b>EW '+fmt(row.equivalent_width_um,5)+' ± '+fmt(row.equivalent_width_sigma_um,5)+' µm</b></div>'+
   '<div class="spectral-cell-metrics"><div><small>Depth</small><b>'+fmt(row.feature_depth,4)+' ± '+fmt(row.feature_depth_sigma,4)+'</b></div>'+
   '<div><small>Continuum ΔEW</small><b>'+fmt(row.continuum_model_EW_difference_um,5)+'</b></div>'+
   '<div><small>LSF FWHM</small><b>'+fmt(resolution.lsf_fwhm_um,5)+' µm</b></div>'+
   '<div><small>Sampling</small><b>'+esc(resolution.sampling_status||"unknown")+'</b></div>'+
   '<div><small>Blending</small><b>'+esc(blend.status||"not assessed")+'</b></div></div>'+
   '<p class="panel-note">'+esc((row.limitations||[]).join(" "))+'</p>'+labs;
  }).join("")+'<p class="panel-note">'+esc(x.warning)+'</p>';
  exportJSON("chronos-feature-evolution.json",x);
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
   prior_match_probability:.9,
   minimum_secure_probability:.8
  });
  state.identityOutput=x;renderIdentityNetwork(x);
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
  const candidates=parse("plan-json","Candidate observation forecasts");
  const alternatives=$("plan-alternative-priors").value.trim()?parse("plan-alternative-priors","Alternative prior sets"):{};
  const x=await call("/observations/plan-candidate",{
   candidates,measurement_sigma:Number($("plan-noise").value),prior_sets:alternatives
  });
  state.plannerOutput=x;renderInformationGain(x);
  const recommended=x.recommended;
  const rows=(x.science_only_ranked||[]).map((item,i)=>{
   const f=item.feasibility||{},rec=f.record||{};
   const verified=f.state==="externally_verified_available";
   return '<article class="planner-candidate"><div class="counter-row"><span>'+(i+1)+'. '+esc(item.candidate_observation_id)+' · '+esc(item.time||"time unspecified")+'</span><b>'+fmt(item.information_gain_bits,3)+' bits</b></div>'+
   '<small>'+(verified?"EXTERNAL FEASIBILITY RECORD VERIFIED":"SCIENCE-ONLY RANKING · FEASIBILITY NOT VERIFIED")+'</small>'+
   (item.measurement_option&&item.measurement_option.wavelength_um!=null?'<small>'+fmt(item.measurement_option.wavelength_um,4)+' µm</small>':"")+
   (rec.source_uri?'<small><a href="'+esc(rec.source_uri)+'" target="_blank" rel="noopener">External source</a> · '+esc(rec.checked_utc||"")+'</small>':"")+
   '<small>Forecast models: '+esc(Object.keys(item.forecast_provenance||{}).join(", "))+'</small></article>';
  }).join("");
  const blocked=(x.blocked_or_unverified||[]).map(row=>'<div class="spectral-source-row"><span>'+esc(row.candidate_observation_id)+'</span><b>'+esc(row.reason)+'</b></div>').join("");
  const sensitivity=Object.entries(x.prior_sensitivity||{}).map(([name,value])=>{
   const ranks=Array.isArray(value)?value.map(v=>v.candidate_observation_id):value.ranked_candidates||[];
   return '<div class="counter-row"><span>'+esc(name)+'</span><small>'+esc(ranks.join(" → ")||"No ranking")+'</small></div>';
  }).join("");
  $("plan-result").innerHTML=(recommended?'<div class="counter-row"><span>Recommended next measurement</span><b>'+esc(recommended.candidate_observation_id)+'</b></div>':'<div class="empty-state">No recommendation. A science ranking is visible, but no complete verified feasible record passed the gate.</div>')+
   '<h4>Science ranking</h4>'+rows+
   (blocked?'<h4>Feasibility gaps</h4>'+blocked:"")+
   (sensitivity?'<h4>Prior sensitivity</h4>'+sensitivity:"")+
   '<p class="panel-note">'+esc(x.feasibility_policy)+' '+esc((x.limitations||[]).join(" "))+'</p>';
  exportJSON("chronos-observation-plan.json",x);
 }catch(e){error("plan-result",e);}
}

async function detector(){
 try{
  needAPI();
  const psf=[[.003,.015,.025,.015,.003],[.015,.075,.11,.075,.015],[.025,.11,.24,.11,.025],[.015,.075,.11,.075,.015],[.003,.015,.025,.015,.003]];
  const size=40,response=[Array.from({length:size},()=>Array(size).fill(1))];
  const x=await call("/causal/forward-exposure",{
   shape:[size,size],mjd:60000,exposure_time_s:1,
   wavelengths_um:[4.5],bandwidths_um:[1.0],wavelength_response:response,
   sources:[{source_id:"SYNTHETIC-CONTROLLED-SOURCE",x:20.3,y:18.7,
     reference_mjd:60000,flux_density_electrons_per_s_um:[Number($("detector-flux").value)]}],
   psf_kernel:psf,background_rate_electrons_per_s:Number($("detector-background").value),
   dark_current_rate_electrons_per_s:1.5,read_noise_electrons:Number($("detector-read").value),
   parameter_provenance:{
    source_spectra:{status:"illustrative",notes:"UI-controlled synthetic source rate"},
    psf:{status:"illustrative",notes:"Generic symmetric example PSF"},
    wavelength_response:{status:"illustrative",notes:"Unity throughput demonstration"},
    background_rate_electrons_per_s:{status:"illustrative"},
    dark_current_rate_electrons_per_s:{status:"illustrative"},
    read_noise_electrons:{status:"illustrative"},
    flat_field:{status:"illustrative"},
    detector_fixed_electrons:{status:"illustrative"}
   },
   seed:9
  });
  state.detectorOutput=x;
  const component=$("decomposition-view").value;
  heat("detector-heatmap",x.components[component]);
  const mean=arr=>{const v=arr.flat().filter(z=>z!==null&&Number.isFinite(Number(z))).map(Number);return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;};
  $("measurement-decomposition").innerHTML=["source_electrons","background_electrons","dark_current_electrons","detector_fixed_electrons","expected_total_electrons","measured_electrons","unexplained_residual_electrons"].map(key=>
   '<div class="counter-row"><span>'+esc(key.replaceAll("_"," "))+'</span><b>'+fmt(mean(x.components[key]),2)+' e⁻/pixel</b></div>'
  ).join("")+'<p class="panel-note">'+esc(x.data_class)+' · calibration ready: '+esc(x.calibration_ready)+'. '+esc(x.limitations.join(" "))+'</p>';
  $("detector-summary").textContent=x.data_class+" · "+component+" · electron-domain synthetic forward model";
 }catch(e){$("detector-summary").textContent=e.message||String(e);}
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
async function assessPopulationCoverage(){
 try{
  needAPI();
  const fields=parse("population-coverage-json","Real archive field records");
  const payload={
   fields,target_class:"young_stellar_object",
   feature_interval_um:pair("population-feature","Feature interval"),
   blue_continuum_um:pair("population-blue","Blue continuum"),
   red_continuum_um:pair("population-red","Red continuum"),
   minimum_independent_fields:5,minimum_epochs_per_source:3,
   minimum_feature_samples:3,minimum_continuum_samples:4,
   minimum_median_snr:5,minimum_completeness:.5
  };
  const x=await call("/population/assess-coverage",payload);
  state.coverageAudit=x;
  $("population-coverage-result").innerHTML='<div class="counter-row"><span>Coverage status</span><b>'+esc(x.status)+'</b></div>'+
   '<div class="counter-row"><span>Eligible fields</span><b>'+x.eligible_field_count+' / '+x.field_count+'</b></div>'+
   '<div class="counter-row"><span>Eligible source records</span><b>'+x.eligible_sources.length+'</b></div>'+
   '<p class="panel-note">'+esc(x.next_step)+' '+esc(x.limitations.join(" "))+'</p>';
  exportJSON("chronos-population-coverage-audit.json",x);
 }catch(e){state.coverageAudit=null;error("population-coverage-result",e);}
}
async function population(){
 try{
  needAPI();
  const fields=parse("population-coverage-json","Real archive field records");
  const digest=$("population-preregistration").value.trim();
  if(!state.coverageAudit?.eligible_for_predeclared_population_protocol){
   await assessPopulationCoverage();
   if(!state.coverageAudit?.eligible_for_predeclared_population_protocol)
    throw Error("Population rate blocked: the archive coverage audit did not pass.");
  }
  const x=await call("/population/yso/rate",{
   fields,preregistration_sha256:digest,target_class:"young_stellar_object",
   feature_interval_um:pair("population-feature","Feature interval"),
   blue_continuum_um:pair("population-blue","Blue continuum"),
   red_continuum_um:pair("population-red","Red continuum"),
   minimum_independent_fields:5,minimum_epochs_per_source:3,
   minimum_feature_samples:3,minimum_continuum_samples:4,
   minimum_median_snr:5,minimum_completeness:.5,draws:10000,seed:4
  });
  const r=x.population_rate.event_rate_per_sqdeg_day;
  $("population-result").innerHTML='<div class="counter-row"><span>Median event rate</span><b>'+fmt(r.median,6)+'</b></div>'+
   '<div class="counter-row"><span>68% interval</span><b>'+fmt(r.lower_68,6)+' – '+fmt(r.upper_68,6)+'</b></div>'+
   '<div class="counter-row"><span>95% interval</span><b>'+fmt(r.lower_95,6)+' – '+fmt(r.upper_95,6)+'</b></div>'+
   '<div class="counter-row"><span>Eligible independent fields</span><b>'+x.coverage_audit.eligible_field_count+'</b></div>'+
   '<p class="panel-note">Protocol digest '+esc(x.preregistration_sha256)+' · '+esc(x.interpretation)+'</p>';
  exportJSON("chronos-yso-population-rate.json",x);
 }catch(e){error("population-result",e);}
}

async function manifest(){
 try{
  needAPI();
  const payload=parse("manifest-json","Archive manifest");
  const x=await call("/evidence/manifest",payload),v=await call("/evidence/manifest/verify",{manifest:x});
  state.manifest=x;
  $("manifest-result").innerHTML=
   '<div class="counter-row"><span>Manifest integrity</span><b>'+(v.valid?"VALID":"INVALID")+'</b></div>'+
   '<div class="counter-row"><span>Complete for reproduction</span><b>'+(v.complete_for_reproduction?"YES":"NO")+'</b></div>'+
   '<div class="counter-row"><span>Input products</span><b>'+x.files.length+'</b></div>'+
   '<pre class="raw-output">'+esc(x.manifest_sha256)+'</pre>'+
   '<p class="panel-note">'+esc((v.completeness_issues||[]).join(", ")||"Required provenance fields are present.")+'</p>'+
   '<button class="button outline" id="download-manifest">Download JSON</button>';
  $("download-manifest").addEventListener("click",()=>download("chronos-manifest.json",x));
 }catch(e){error("manifest-result",e);}
}

async function evidenceGraph(){
 try{needAPI();if(!state.analysis)await analyze();if(!state.analysis)throw Error("Run model comparison first.");
 const modelRuns=(state.analysis.relative_model_support||[]).map((m,i)=>({
  run_id:"model-"+i,model:m.name,score:m.bic,score_type:"BIC",
  observation_ids:state.observations.map((row,j)=>String(row.observation_id||row.measurement_id||j))
 }));
 const failedTests=(state.analysis.rejected_models||[]).map(row=>({name:row.model,status:"rejected",reason:row.reason}))
  .concat((state.analysis.abstention_reasons||[]).map(reason=>({name:"abstention",status:"not_passed",reason})));
 const x=await call("/evidence/graph",{
  candidate_id:state.observations[0].candidate_id||"candidate",
  observations:state.observations,analysis:state.analysis,manifest:state.manifest,
  model_runs:modelRuns,counterfactuals:[],failed_tests:failedTests,
  environment:state.manifest?.software||{},
  code_commit:state.manifest?.software?.pipeline_commit||null
 });
 state.evidenceGraph=x;renderEvidenceGraph(x);
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
$("spectral-heatmap").addEventListener("keydown",inspectSpectralCell);
$("spectral-heatmap").setAttribute("tabindex","0");
$("run-plan").addEventListener("click",planner);$("run-detector").addEventListener("click",detector);
$("run-benchmark").addEventListener("click",benchmark);$("run-baselines").addEventListener("click",baselines);
$("run-population").addEventListener("click",population);$("create-manifest").addEventListener("click",manifest);
$("create-evidence-graph").addEventListener("click",evidenceGraph);$("export-investigation-package").addEventListener("click",exportInvestigationPackage);
async function searchCandidates(){
 try{
  needAPI();
  const result=await call("/workspace/candidates",{
   observations:state.observations,query:$("candidate-query").value,
   dataset_class:$("candidate-class-filter").value||null,
   calibration_group:$("candidate-cal-filter").value||null
  });
  $("candidate-search-results").innerHTML=result.candidates.map(row=>
   '<div class="counter-row"><span><b>'+esc(row.candidate_id)+'</b><small>'+esc(row.data_class)+' · '+row.observation_count+' rows · '+row.wavelength_count+' wavelengths</small></span><button class="button outline" data-save-candidate="'+esc(row.candidate_id)+'">Save</button></div>'
  ).join("")||'<div class="empty-state">No matching candidates in the loaded observation rows.</div>';
  $("candidate-search-results").querySelectorAll("[data-save-candidate]").forEach(button=>button.addEventListener("click",()=>{
   const id=button.dataset.saveCandidate;if(!state.shortlist.includes(id))state.shortlist.push(id);saveShortlist();
  }));
 }catch(e){error("candidate-search-results",e);}
}
async function compareCandidates(){
 try{
  needAPI();const ids=[$("compare-a").value,$("compare-b").value];
  if(!ids[0]||!ids[1])throw Error("Select two shortlisted candidate IDs.");
  const result=await call("/workspace/compare",{candidate_ids:ids,observations:state.observations});
  $("candidate-compare-results").innerHTML=result.comparisons.map(row=>
   '<div class="counter-row"><span>'+esc(row.candidate_id)+' · '+esc(row.data_class)+' · '+row.observation_count+' rows</span><b>'+esc(row.analysis.verdict||"unknown")+'</b></div>'
  ).join("")+'<p class="panel-note">'+esc(result.warning||"Independent candidate analyses.")+'</p>';
  exportJSON("chronos-two-candidate-comparison.json",result);
 }catch(e){error("candidate-compare-results",e);}
}
function shareShortlist(){
 const params=new URLSearchParams(location.hash.slice(1));
 params.set("shortlist",state.shortlist.join(","));
 const url=location.origin+location.pathname+"#"+params.toString();
 if(navigator.clipboard&&navigator.clipboard.writeText){
  navigator.clipboard.writeText(url).then(
   ()=>$("run-status").textContent="Shareable shortlist URL copied",
   ()=>$("run-status").textContent="Clipboard unavailable; copy the address-bar URL"
  );
 }else{$("run-status").textContent="Clipboard unavailable; copy the address-bar URL";}
}
function exportObservationsCsv(){
 const rows=state.observations;if(!rows.length)return;
 const keys=[...new Set(rows.flatMap(row=>Object.keys(row)))];
 const quote=value=>'"'+String(value===null||value===undefined?"":value).replace(/"/g,'""')+'"';
 const csv=[keys.map(quote).join(","),...rows.map(row=>keys.map(key=>
  quote(row[key]&&typeof row[key]==="object"?JSON.stringify(row[key]):row[key])
 ).join(","))].join("\n");
 const url=URL.createObjectURL(new Blob([csv],{type:"text/csv"})),a=document.createElement("a");
 a.href=url;a.download="chronos-observations.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function exportHeatmapFigure(){
 if(!state.spectral){$("spectrum-summary").textContent="Run spectral reconstruction before exporting a figure.";return;}
 const a=document.createElement("a");a.href=$("spectral-heatmap").toDataURL("image/png");a.download="chronos-spectral-time-wavelength.png";a.click();
}
function loadShortlistOnStartup(){loadShortlist();}
$("search-candidates").addEventListener("click",searchCandidates);
$("compare-candidates").addEventListener("click",compareCandidates);
$("share-shortlist").addEventListener("click",shareShortlist);
$("clear-shortlist").addEventListener("click",()=>{state.shortlist=[];saveShortlist();});
$("export-observations-json").addEventListener("click",()=>exportJSON("chronos-observations.json",state.observations));
$("export-observations-csv").addEventListener("click",exportObservationsCsv);
$("export-heatmap-figure").addEventListener("click",exportHeatmapFigure);
$("assess-population-coverage").addEventListener("click",assessPopulationCoverage);
$("decomposition-view").addEventListener("change",()=>{
 if(state.detectorOutput)heat("detector-heatmap",state.detectorOutput.components[$("decomposition-view").value]);
});
$("observation-timeline").addEventListener("click",selectExposure);
$("observation-timeline").addEventListener("keydown",event=>{
 if(event.key==="Enter"||event.key===" "){
  event.preventDefault();const rect=$("observation-timeline").getBoundingClientRect();
  selectExposure({clientX:rect.left+rect.width/2});
 }
});

loadShortlistOnStartup();
status();
})();