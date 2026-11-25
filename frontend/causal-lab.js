(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={observations:[],analysis:null,manifest:null,apiReady:false};
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
function updateRows(rows){
 state.observations=rows;$("observations-json").value=pretty(rows);
 const ok=rows.filter(x=>x.valid!==false),times=ok.map(x=>Number(x.mjd));
 $("data-class").textContent=ok.some(x=>String(x.calibration_group||"").startsWith("SYNTHETIC"))?"Synthetic fixture":"Supplied measurements";
 $("observation-count").textContent=ok.length;$("time-baseline").textContent=times.length?fmt(Math.max(...times)-Math.min(...times),1)+" d":"—";
 $("wave-count").textContent=new Set(ok.map(x=>x.wavelength_um)).size;
 track("sky-chart",ok,"sky");track("detector-chart",ok,"detector");
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
function heat(id,matrix){
 const c=$(id),g=c.getContext("2d"),h=matrix.length,w=matrix[0]?.length||0;g.clearRect(0,0,c.width,c.height);g.fillStyle="#071721";g.fillRect(0,0,c.width,c.height);
 const a=matrix.flat().map(Number).filter(Number.isFinite);if(!a.length||!w){g.fillStyle="#91a8ab";g.fillText("No supported measurements",18,30);return;}
 const lo=Math.min(...a),span=Math.max(Math.max(...a)-lo,1e-12),cw=c.width/w,ch=c.height/h;
 matrix.forEach((row,y)=>row.forEach((v,x)=>{if(!Number.isFinite(Number(v))){g.fillStyle="#10232d";g.fillRect(x*cw,y*ch,cw+.4,ch+.4);}else{const t=(v-lo)/span;g.fillStyle="hsl("+(196-48*t)+" 48% "+(22+44*t)+"%)";g.fillRect(x*cw,y*ch,cw+.4,ch+.4);}}));
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
 try{needAPI();const rows=state.observations.filter(r=>r.valid!==false);if(rows.length<3)throw Error("Load observations first.");
 const w=rows.map(r=>Number(r.wavelength_um)),t=rows.map(r=>Number(r.mjd)),a=Math.min(...w),b=Math.max(...w),c=Math.min(...t),d=Math.max(...t);
 const groups=[...new Set(rows.map(r=>r.calibration_group))];if(groups.length!==1||!groups[0])throw Error("Use one calibration group per reconstruction.");
 const x=await call("/spectrotemporal/reconstruct",{samples:rows,wavelength_grid_um:Array.from({length:36},(_,i)=>a+(b-a)*i/35),time_grid_mjd:Array.from({length:20},(_,i)=>c+(d-c)*i/19),wavelength_bandwidth_um:Number($("wave-bandwidth").value),time_bandwidth_days:Number($("time-bandwidth").value),min_neighbors:2,calibration_group:groups[0]});
 heat("spectral-heatmap",x.flux);const count=x.valid.flat().filter(Boolean).length;$("spectrum-summary").textContent=count+" supported grid cells. "+x.missing_data_policy+" "+x.limitations.join(" ");
 }catch(e){$("spectrum-summary").textContent=e.message||String(e);}
}
async function featureEvolution(){
 try{needAPI();const epochs=parse("feature-epochs","Epoch spectra"),feature=pair("feature-interval","Feature interval"),blue=pair("feature-blue","Blue continuum"),red=pair("feature-red","Red continuum");
 const x=await call("/spectrotemporal/feature-evolution",{epochs,feature_interval_um:feature,continuum_intervals_um:[blue,red]});
 $("feature-evolution-result").innerHTML=x.epochs.map(r=>'<div class="counter-row"><span>'+esc(r.epoch_id)+' · MJD '+esc(r.mjd)+'</span><b>EW '+fmt(r.equivalent_width_um,5)+' µm</b></div>').join("")+'<p class="panel-note">'+esc(x.warning)+'</p>';}
 catch(e){error("feature-evolution-result",e);}
}
async function identity(){
 try{needAPI();const x=await call("/identity/associate",{candidate:parse("identity-candidate","Candidate"),catalogue_rows:parse("identity-catalogue","Catalogue"),search_radius_arcsec:10,background_density_per_arcsec2:.001,prior_match_probability:.9});
 $("identity-result").innerHTML='<div class="counter-row"><span>Status</span><b>'+esc(x.status)+'</b></div><div class="counter-row"><span>No counterpart</span><b>'+fmt(x.no_counterpart_probability)+'</b></div>'+x.matches.map(m=>'<div class="counter-row"><span>'+esc(m.source_id)+'<small style="display:block;color:#728d93">'+fmt(m.separation_arcsec,2)+' arcsec</small></span><b>'+(100*m.association_probability).toFixed(1)+'%</b></div>').join("")+'<p class="panel-note">'+esc(x.limitations.join(" "))+'</p>';}
 catch(e){error("identity-result",e);}
}
async function planner(){
 try{needAPI();const x=await call("/observations/plan",{candidates:parse("plan-json","Observation forecasts"),measurement_sigma:Number($("plan-noise").value)});
 $("plan-result").innerHTML=x.ranked.map((m,i)=>'<div class="counter-row"><span>'+(i+1)+'. '+esc(m.time||"Unnamed")+'</span><b>'+fmt(m.information_gain,3)+' bits</b></div>').join("")+'<p class="panel-note">'+esc(x.limitations.join(" "))+'</p>';}
 catch(e){error("plan-result",e);}
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
 $("evidence-graph-result").innerHTML='<div class="counter-row"><span>Evidence nodes</span><b>'+x.nodes.length+'</b></div><div class="counter-row"><span>Evidence links</span><b>'+x.edges.length+'</b></div><div class="counter-row"><span>Graph SHA-256</span><b>'+esc(x.graph_sha256.slice(0,18))+'…</b></div><button class="button outline" id="download-graph">Download graph JSON</button>';$("download-graph").addEventListener("click",()=>download("chronos-evidence-graph.json",x));}
 catch(e){error("evidence-graph-result",e);}
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
$("run-plan").addEventListener("click",planner);$("run-detector").addEventListener("click",detector);
$("run-benchmark").addEventListener("click",benchmark);$("run-baselines").addEventListener("click",baselines);
$("run-population").addEventListener("click",population);$("create-manifest").addEventListener("click",manifest);
$("create-evidence-graph").addEventListener("click",evidenceGraph);status();
})();