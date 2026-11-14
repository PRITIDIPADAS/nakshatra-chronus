/* Lab drawer: extra tools. Uses the globals of index.html: $, api, lang, ex, SA, SB, key, card. */
(function(){
const X={doc:['Check the live archive','লাইভ আর্কাইভ পরীক্ষা'],lapse:['Fair time lapse','ন্যায্য টাইম ল্যাপস'],bt:['Can you beat the machine?','যন্ত্রকে হারাতে পারবেন?'],
px:['How far can SPHEREx see a Planet X?','SPHEREx কত দূরের প্ল্যানেট এক্স দেখতে পারে?'],ps:['Search a practice sky for a Planet X','অনুশীলনের আকাশে প্ল্যানেট এক্স খুঁজুন'],
mv:['Known asteroids here','এখানকার পরিচিত গ্রহাণু'],tm:['Where was this star 70 years ago?','৭০ বছর আগে তারাটি কোথায় ছিল?'],fz:['Freeze the rules','নিয়ম ফ্রিজ করুন']};
const bar=$('labbar'),out=$('labout'),box=$('labx');
bar.innerHTML=Object.keys(X).map(k=>`<button id="lab_${k}"></button>`).join('')+
' <label>AU <input id="pd" type="text" value="500" size="4"></label><label>R <input id="pr" type="text" value="3" size="2"></label><label>albedo <input id="pa" type="text" value="0.3" size="3"></label>';
const name=()=>{for(const k in X)$('lab_'+k).textContent=X[k][lang=='bn'?1:0]};name();
$('lang').addEventListener('change',name);
let lt=null;
const say=x=>{if(lt){clearInterval(lt);lt=null}box.innerHTML='';out.textContent=typeof x=='string'?x:JSON.stringify(x,null,1)};
const run=(k,f)=>$('lab_'+k).onclick=async()=>{try{await f()}catch(e){say(e.message)}};
const need=()=>{if(!ex.length)throw new Error(lang=='bn'?'আগে একটি তারা বেছে নিন।':'Choose a star first.')};

run('doc',async()=>{say('Asking the archive. This needs internet.');const r=await api('/api/doctor?t='+(key||'barnard'));
say(r.map(s=>`${s.ok?'OK  ':'FAIL'}  ${s.step}\n      ${s.detail}`).join('\n')+'\n\n'+(r.every(s=>s.ok)?'Every step works. Live SPHEREx mode is ready.':'A step failed. The practice sky still works. The text above says which step and why.'))});

run('lapse',async()=>{need();if(lt)return say('Stopped.');if(SA==null)throw new Error('Pick a dot in step 1 first.');
const Lp=await api('/api/lapse?ref='+SA);if(Lp.length<2)return say('This picture has no fair partner. Pick another dot.');
say(`${Lp.length} pictures with the same color, in date order. Each one is lined up with the first. Press the button again to stop.`);
box.innerHTML='<img id="lapimg" alt="Fair time lapse" style="width:min(100%,392px);image-rendering:pixelated;border-radius:.4em"><p id="lapcap"></p>';
let k=0;const step=()=>{if(!$('lapimg'))return;const q=Lp[k%Lp.length];k++;$('lapimg').src=`/api/frame/${q.i}.png?to=${SA}`;$('lapcap').textContent=`Day ${ex[q.i].day.toFixed(0)}, ${ex[q.i].lam.toFixed(3)} micron, pair score ${q.score}`};step();lt=setInterval(step,1000)});

run('mv',async()=>{need();say(await api('/api/movers?i='+(SB!=null?SB:SA!=null?SA:0)))});
run('px',async()=>{const r=await api(`/api/planetx?d=${$('pd').value}&radius=${$('pr').value}&albedo=${$('pa').value}`);
say(`A planet of ${$('pr').value} Earth radii at ${$('pd').value} AU has magnitude ${r.magnitude_at_distance.toFixed(1)}.\nOne SPHEREx picture reaches such a planet out to about ${Math.round(r.single_visit_reach_au)} AU. Four pictures together reach about ${Math.round(r.four_visit_reach_au)} AU.\nIn six months the planet shifts by ${Math.round(r.parallax_amplitude_pixels)} pixels, because the Earth moves around the Sun.\n\n${r.note}`)});
run('ps',async()=>{say('Searching hundreds of tracks through 24 pictures. This takes a few seconds.');const r=await api(`/api/planetsearch?inject=1&d=${$('pd').value}&q=2`);card.planet_search=r;const b=r.top[0];
say(`${r.label}\nA planet was hidden at ${r.injected_distance_au} AU. In each picture it is only ${r.injected_snr_per_frame} times the noise, so no single picture shows it.\nCHRONOS added the ${r.frames} pictures along ${r.tracks_tested} possible tracks.\nBest track: ${b.d} AU, combined signal ${b.snr.toFixed(1)} times the noise. Expected false alarms at this level: ${b.expected_false_alarms.toExponential(1)}.\n\n${r.note}`)});
run('fz',async()=>{const r=await api('/api/protocol'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(r,null,1)],{type:'application/json'}));a.download='chronos_protocol_frozen.json';a.click();
say('Saved. The file holds every threshold and a fingerprint of the code.\nSeal: '+r.seal+'\n\n'+r.rule)});

let al=null;
run('tm',async()=>{const P=await api('/api/path?t='+(key||'barnard'));say(`${P.name} moved about ${Math.round(P.moved_arcsec)} arcseconds in 70 years. The marks show where the catalog puts it at 70, 35, 28, 16, 10 and 0 years ago. The old sky images come from other telescopes. This tool needs internet.`);
box.innerHTML='<select id="svs"><option value="P/DSS2/color">Photographic plates</option><option value="P/2MASS/color">Near infrared survey</option><option value="P/allWISE/color">WISE</option></select><div id="aladin" style="width:100%;height:380px;margin-top:.5em"></div>';
if(!window.A||!window.A.aladin)await new Promise((ok,no)=>{const s=document.createElement('script');s.src='https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js';s.onload=ok;s.onerror=()=>no(new Error('The sky atlas did not load. Check the internet connection.'));document.head.appendChild(s)});
const AL=window.A;await AL.init;const p=P.points[P.points.length-1];al=AL.aladin('#aladin',{survey:'P/DSS2/color',fov:0.15,target:`${p.ra} ${p.dec}`});
const cat=AL.catalog({name:'Catalog path',sourceSize:14,color:'#c4432b'});al.addCatalog(cat);cat.addSources(P.points.map(q=>AL.source(q.ra,q.dec,{name:q.years_ago+' years ago'})));
$('svs').onchange=()=>al.setImageSurvey($('svs').value)});

let bo=[],bi=0,bres=[];
function nextB(){if(lt){clearInterval(lt);lt=null}out.textContent='';
if(bi>=bo.length){const lv=[4,6,8,12,20].map(q=>{const r=bres.filter(x=>x.snr==q);return`  ${q} times the noise: you ${r.filter(x=>x.you==x.truth).length} of ${r.length}, machine ${r.filter(x=>x.algo==x.truth).length} of ${r.length}`}).join('\n');
card.blind_test=bres;box.innerHTML='';out.textContent=`Done. You were right ${bres.filter(r=>r.you==r.truth).length} of ${bres.length} times. The machine was right ${bres.filter(r=>r.algo==r.truth).length} of ${bres.length} times.\n${lv}\nThis is a small pilot test on practice images.`;return}
const k=bo[bi];
box.innerHTML=`<p>Pair ${bi+1} of ${bo.length}. One star may have moved. Did it?</p><img id="bimg" src="/api/blind/${k}/0.png" alt="Practice image" style="width:min(100%,300px);image-rendering:pixelated;border-radius:.4em"><div class="tools"><button id="bfl">Blink</button><button id="by" class="main">It moved</button><button id="bn" class="main">Nothing moved</button></div><p id="bsay" role="status"></p>`;
let f=0;$('bfl').onclick=()=>{f^=1;$('bimg').src=`/api/blind/${k}/${f}.png`};
const ans=async s=>{const r=await api(`/api/blind/${k}/answer`);bres.push({you:s,truth:r.moved,algo:r.algo,snr:r.snr});$('by').disabled=$('bn').disabled=true;
$('bsay').innerHTML=`${s==r.moved?'Correct':'Not correct'}. Truth: ${r.moved?'it moved':'nothing moved'}. The star was ${r.snr} times the noise. The machine said: ${r.algo?'it moved':'nothing moved'}. <button id="bx">Next</button>`;$('bx').onclick=()=>{bi++;nextB()}};
$('by').onclick=()=>ans(true);$('bn').onclick=()=>ans(false)}
run('bt',async()=>{bo=[...Array(20).keys()].sort(()=>Math.random()-.5);bi=0;bres=[];nextB()});
})();
