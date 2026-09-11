'use strict';
const $ = (s) => document.querySelector(s);
const escape = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const categories = {factual_high_certainty:'Factual · high certainty', factual_low_resource:'Bangladesh-specific', temporally_unstable:'Temporally unstable', ambiguous_contested:'Ambiguous / contested', unanswerable_adversarial:'Unanswerable / adversarial', code_switched:'Bengali–English mixed'};
const defaults = {gemini:'gemini-3.5-flash-lite',groq:'qwen/qwen3.8-27b',ollama:''};
const state = {view:'results', data:null, questions:[], qid:null, dataset:'dataset/draft-v0.1-batch01.jsonl', report:null, run:null, category:'', query:''};
let noticeTimer, polling = false, lastJobStatus;
const today = () => new Date().toLocaleDateString('en-CA');
function notify(text,error=false) { const el=$('#notice');el.textContent=text;el.className=error?'error':'';el.hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>el.hidden=true,9000); }
async function api(path, data) {
  const options=data ? {method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.data.token},body:JSON.stringify(data)} : {};
  const response=await fetch(path,options);const value=await response.json();
  if(!response.ok) throw new Error(value.error || 'Request failed.');return value;
}
function title(n,heading,intro){return `<p class="eyebrow">${n} / Research workspace</p><h1>${heading}</h1><p class="intro">${intro}</p>`;}
function options(values,selected){return values.map(([v,t])=>`<option value="${escape(v)}" ${v===selected?'selected':''}>${escape(t)}</option>`).join('');}
function boolField(name,label){return `<label>${label}<select name="${name}" required><option value="">Choose…</option><option value="true">Yes</option><option value="false">No</option></select></label>`;}
function identity(){return `<label>Your reviewer ID<input name="reviewer_id" required maxlength="120" placeholder="An ID attributable to you" autocomplete="off"></label><label>Review date<input name="reviewed_at" type="date" value="${today()}" required></label>`;}
function artifact(report,file){return `/artifact?report=${encodeURIComponent(report)}&file=${encodeURIComponent(file)}`;}
function metric(m){if(!m || m.estimate===null)return 'Unavailable';return Number(m.estimate).toFixed(3);}
function interval(m){return m?.ci95 ? `95% CI ${m.ci95.map(v=>Number(v).toFixed(3)).join(' – ')}`:'No estimable interval';}
async function refresh(){state.data=await api('/api/state');renderJob(state.data.job);}
function nav(){document.querySelectorAll('[data-view]').forEach(el=>{el.classList.toggle('active',el.dataset.view===state.view);el.setAttribute('aria-current',el.dataset.view===state.view?'page':'false');});}
async function render(){nav();if(state.view==='results')await results();if(state.view==='dataset')await dataset();if(state.view==='runs')runs();if(state.view==='grading')await grading();}

async function results(){
  const d=state.data, archive=d.runs.filter(r=>!r.local), batch=d.datasets.find(x=>x.id===state.dataset);
  const count=archive.reduce((a,r)=>a+r.completed,0), judged=archive.reduce((a,r)=>a+r.judged,0);
  $('#content').innerHTML=title('01','Reliability, made measurable.','Explore the evidence behind model confidence in Bengali. Review status and uncertainty stay visible at every step.')+
    `<div class="stats"><div class="stat"><span class="caption">DRAFT CANDIDATES</span><span class="value">${batch?.count??0}</span><small>First release target: 400–600</small></div><div class="stat"><span class="caption">ARCHIVED ANSWERS</span><span class="value">${count}</span><small>Across ${archive.length} model runs</small></div><div class="stat"><span class="caption">MACHINE GRADES</span><span class="value">${judged}<small> / ${count}</small></span><small>Smoke-test judging is incomplete</small></div><div class="stat"><span class="caption">RESEARCH STATUS</span><span class="value">Preview</span><small>Human validation required</small></div></div>
    <div class="callout"><strong>PRELIMINARY, UNREVIEWED DATA.</strong> The archived smoke results use an incompletely graded draft. They cannot establish a model ranking or a validated research finding.</div>
    <div class="toolbar"><label>Report<select id="report-choice">${options(d.reports.map(p=>[p,p.replace('report/','')]),state.report||d.reports[0])}</select></label></div><div id="report-detail"></div>`;
  if(!d.reports.length){$('#report-detail').innerHTML='<div class="empty">Generate a report from a graded local run to see results here.</div>';return;}
  state.report=d.reports.includes(state.report)?state.report:d.reports[0];await reportDetail();
}
async function reportDetail(){
  const report=await api('/api/report?report='+encodeURIComponent(state.report));state.reportData=report;
  const models=[...new Set(Object.values(report.summaries).map(s=>`${s.provider}/${s.model}`))];
  $('#report-detail').innerHTML=`<section class="panel"><div class="panel-title"><h2>Calibration & behavior</h2><span class="badge amber">${escape(report.label)}</span></div><div class="toolbar"><label>Model<select id="metric-model">${options(models.map(m=>[m,m]),models[0])}</select></label><label>Category<select id="metric-category"><option value="overall">Overall graded subset</option>${options(Object.entries(categories),'')}</select></label></div><div id="metric-detail"></div><div class="links">${['REPORT.md','metrics.csv','metrics.json'].map(f=>`<a href="${artifact(state.report,f)}" target="_blank" rel="noreferrer">${f==='REPORT.md'?'Read full report':f==='metrics.csv'?'Download CSV':'Inspect JSON'} ↗</a>`).join('')}</div></section>
    <section class="panel"><div class="panel-title"><h2>Where confidence meets correctness</h2><span class="muted">${report.resamples.toLocaleString()} bootstrap resamples · seed ${report.seed}</span></div><div class="split"><div class="chart-frame"><img class="chart" src="${artifact(state.report,'calibration.png')}" alt="Calibration diagram from this report; preliminary data"></div><div class="chart-frame"><img class="chart" src="${artifact(state.report,'risk_coverage.png')}" alt="Risk–coverage curve with bootstrap confidence intervals; preliminary data"></div></div></section>
    <section class="panel"><h2>Human validation</h2><div class="scroll"><table><thead><tr><th>EVALUATED MODEL</th><th>HUMAN GRADES</th><th>JUDGE AGREEMENT</th><th>STATUS</th></tr></thead><tbody>${report.inputs.map(i=>`<tr><td class="model">${escape(i.manifest.plan.config.model)}</td><td>${i.agreement.human_completed} / ${i.agreement.queue_size}</td><td>${metric(i.agreement.agreement.grade)}<br><span class="muted">${interval(i.agreement.agreement.grade)}</span></td><td>${escape(i.agreement.status)}</td></tr>`).join('')}</tbody></table></div><p class="muted">Missing human grades mean agreement is unavailable. Dataset review and response grading are separate tasks.</p></section>`;
  metrics();
}
function metrics(){
  const model=$('#metric-model').value,cat=$('#metric-category').value,s=state.reportData.summaries[`${model}/${cat}`];
  if(!s){$('#metric-detail').innerHTML='<div class="empty">No scored responses in this category. No estimate is inferred.</div>';return;}
  const fields=[['ece_confidence','Calibration error (ECE)'],['brier_confidence','Brier score'],['hallucination_rate','Hallucination rate'],['abstention_recall_category5','Abstention recall · cat. 5']];
  $('#metric-detail').innerHTML=`<div class="stats">${fields.map(([k,label])=>`<div class="stat"><span class="caption">${label}</span><span class="value">${metric(s.metrics[k])}</span><small>${interval(s.metrics[k])}</small></div>`).join('')}</div><p class="muted">${s.n_scored} graded answers · ${s.n_calibration} factual calibration items · ${s.n_hallucination_denominator} hallucination-test items. Rates are fractions from 0 to 1. Lower ECE, Brier and hallucination rates are better.</p>`;
}

async function dataset(){
  state.questions=await api('/api/questions?dataset='+encodeURIComponent(state.dataset));
  if(!state.questions.some(q=>q.id===state.qid))state.qid=state.questions[0]?.id;
  $('#content').innerHTML=title('02','Build trust, one question at a time.','Inspect the Bengali phrasing, reference answer, and source notes. Submit only reviews you personally perform as a native Bengali speaker.')+
    `<div class="toolbar"><label>Question set<select id="dataset-choice">${options(state.data.datasets.map(d=>[d.id,`${d.id.split('/').pop()} · ${d.count} questions`]),state.dataset)}</select></label><label>Category<select id="category-filter"><option value="">All six categories</option>${options(Object.entries(categories),state.category)}</select></label><label>Find a question<input id="question-search" type="search" value="${escape(state.query)}" placeholder="Bengali text, English gloss, or ID"></label></div>
    <div class="review-layout"><div id="question-list" class="question-list" aria-label="Questions"></div><section id="question-detail" class="panel review-card"></section></div>`;
  questionList();questionDetail();
}
function questionList(){
  const rows=state.questions.filter(q=>(!state.category||q.category===state.category)&&`${q.id} ${q.question_bn} ${q.question_en_gloss}`.toLowerCase().includes(state.query.toLowerCase()));
  if(!rows.some(q=>q.id===state.qid)){state.qid=rows[0]?.id;questionDetail();}
  $('#question-list').innerHTML=rows.length?rows.map(q=>`<button data-question="${q.id}" class="${q.id===state.qid?'active':''}" aria-pressed="${q.id===state.qid}"><small>${q.id} · ${escape(q.difficulty_tier)}</small><span class="preview" lang="bn">${escape(q.question_bn)}</span></button>`).join(''):'<div class="empty">No matching questions.</div>';
}
function questionDetail(){
  const q=state.questions.find(q=>q.id===state.qid);if(!q){$('#question-detail').innerHTML='<div class="empty">Choose a matching question to review.</div>';return;}
  $('#question-detail').innerHTML=`<div class="panel-title"><span class="eyebrow">${q.id}</span><span class="badge amber">${q.reviewed_by.length<2?'Awaiting human review':'Review IDs present'}</span></div><h3>${escape(categories[q.category])}</h3><p class="bengali" lang="bn">${escape(q.question_bn)}</p><p class="muted">${escape(q.question_en_gloss)}</p><div class="reference"><strong>Expected behavior · ${escape(q.expected_behavior)}</strong>${escape(q.ground_truth_answer??'No concrete reference answer — grade the specified behavior.')}</div><div class="reference"><strong>Source / justification</strong>${escape(q.source_note)}</div><details><summary>Construction notes</summary><div class="reference">${escape(q.notes)}</div></details><div class="divider"></div><h2>Your independent review</h2><p class="muted">Other reviewers’ decisions are not shown here. Submissions preserve your first decision and do not automatically update the dataset’s review IDs.</p>
    <form id="review-form" class="grid-form">${identity()}<label class="wide">Decision<select name="decision" required><option value="">Choose after reviewing…</option><option value="accept">Accept</option><option value="revise">Needs revision</option><option value="reject">Reject</option></select></label>${boolField('natural_bengali','Is the Bengali phrasing natural?')}${boolField('source_verified','Did you verify the reference / source?')}${boolField('premise_checked','Is the factual or false premise justified?')}${boolField('behavior_appropriate','Is the expected behavior appropriate?')}<label class="wide">Rationale and source verification<textarea name="rationale" required maxlength="4000" placeholder="Record evidence, corrections, or why you accept the item."></textarea></label><label class="check wide"><input type="checkbox" name="native" required>I am a native Bengali speaker and personally performed this independent review.</label><div class="wide"><button class="primary" type="submit">Save my review</button></div></form>`;
}

function providerFields(judge=false){return `<label>Provider<select name="provider" id="${judge?'judge':'run'}-provider">${options([['gemini','Gemini · free tier'],['groq','Groq · free tier'],['ollama','Ollama · local']],'gemini')}</select></label><label>Model ID<input name="model" id="${judge?'judge':'run'}-model" value="${judge?'gemini-3.5-flash':defaults.gemini}" required maxlength="160" placeholder="Exact installed / available model ID"></label><label>Seconds between requests<input name="interval" type="number" value="6" min="0" max="3600" required></label><label>Maximum output tokens<input name="max_tokens" type="number" value="1024" min="128" max="8192" required></label>`;}
function runOptions(localOnly=false){return state.data.runs.filter(r=>!localOnly||r.local).map(r=>[r.id,`${r.config.model} · ${r.id.split('/').pop()}${r.local?'':' (archive)'}`]);}
function runs(){
  const creds=state.data.credentials;
  $('#content').innerHTML=title('03','Run carefully. Keep the evidence.','Launch or resume an evaluation with the existing pipeline. Every answer is logged before scoring, and quota errors stop the run.')+
    `<div class="row"><span class="badge">Gemini key: ${creds.gemini?'configured':'missing'}</span><span class="badge">Groq key: ${creds.groq?'configured':'missing'}</span><span class="badge">Ollama: local server required</span></div>
    <section class="panel"><div class="panel-title"><h2>Saved evaluations</h2><button class="secondary" data-action="refresh">Refresh</button></div>${state.data.runs.length?state.data.runs.map(r=>`<div class="run-card"><div><h3>${escape(r.config.model)} <span class="badge ${r.local?'':'amber'}">${r.local?'Local working run':'Read-only archive'}</span></h3><div class="meta">${r.completed}/${r.planned} answers · ${r.judged} machine grades · ${r.human} assessed human grades · ${escape(r.status)}</div><div class="path">${escape(r.id)}</div></div><div class="actions">${r.local?`<button class="secondary" data-action="resume" data-run="${escape(r.id)}">Resume generation</button><button class="secondary" data-action="assess" data-run="${escape(r.id)}">Prepare / assess queue</button><button class="secondary" data-action="report" data-run="${escape(r.id)}">Generate report</button><button class="secondary" data-action="expand" data-run="${escape(r.id)}">Expand human queue</button>`:`<button class="secondary" data-action="clone" data-run="${escape(r.id)}">Create local working copy ↗</button>`}</div></div>`).join(''):'<div class="empty">No runs yet. Start one below.</div>'}</section>
    <div class="split"><section class="panel"><h2>New evaluation</h2><p class="muted">24 questions × (1 primary + 3 samples) = 96 generation requests. Normal full evaluations use 10 samples. Check your free quota before starting.</p><form id="run-form" class="grid-form"><label class="wide">Run name<input name="name" required pattern="[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}" placeholder="bengali-pilot-01"></label><label class="wide">Dataset<select name="dataset">${options(state.data.datasets.map(d=>[d.id,d.id.split('/').pop()]),state.dataset)}</select></label>${providerFields()}<label>Questions<input name="limit" type="number" min="1" max="600" value="24" required></label><label>Samples per question<input name="samples" type="number" min="2" max="10" value="3" required></label><label class="check wide"><input type="checkbox" name="allow_unreviewed">Allow unreviewed drafts; label all outputs PRELIMINARY, UNREVIEWED DATA.</label><label class="check wide"><input type="checkbox" required>I will use a free-tier account with billing disabled, or a locally installed Ollama model.</label><div class="wide"><button class="primary" type="submit">Start evaluation</button></div></form></section>
    <section class="panel"><h2>Initial machine judging</h2><p class="muted">Choose a separate judge model. Resuming preserves the original judge configuration and existing grades. Human validation is still required.</p><form id="judge-form" class="grid-form"><label class="wide">Local run<select name="run" required><option value="">Choose a local working run…</option>${options(runOptions(true),state.run)}</select></label>${providerFields(true)}<label class="check wide"><input type="checkbox" required>I will use free-tier or local inference for this judging pass.</label><div class="wide"><button class="primary" type="submit">Start / resume judging</button></div></form><div class="callout">The archived Gemini judge reached its 20 requests/project/model/day free quota. The saved runs still have 27 pending grades. This interface does not bypass that quota.</div></section></div>`;
}

async function grading(){
  const available=runOptions();if(!available.some(([id])=>id===state.run))state.run=available.find(([id])=>id.startsWith('results/local/'))?.[0]||available[0]?.[0];
  $('#content').innerHTML=title('04','A human check on machine judgment.','Grade the answer against its reference before viewing judge labels. Your first decisions are preserved for the agreement calculation.')+
    `<div class="toolbar"><label>Evaluation run<select id="grading-run">${options(available,state.run)}</select></label><button class="secondary" data-action="reload-grading">Refresh queue</button></div><div id="grading-detail"></div>`;
  if(!state.run){$('#grading-detail').innerHTML='<div class="empty">Run an evaluation and prepare its human queue first.</div>';return;}
  try{
    const queue=await api('/api/queue?run='+encodeURIComponent(state.run));state.queue=queue;
    const local=state.data.runs.find(r=>r.id===state.run)?.local;
    const q=queue.rows[0];
    if(!q){$('#grading-detail').innerHTML=`<section class="panel"><h2>All queued answers have a human grade.</h2><p class="muted">${queue.completed} submissions. Refresh assessment to calculate agreement and identify unresolved disagreements.</p>${local?`<button class="primary" data-action="assess" data-run="${escape(state.run)}">Refresh assessment</button>`:''}</section>`;return;}
    $('#grading-detail').innerHTML=`${!local?`<div class="callout">This archived queue is read-only. Create a local working copy in Evaluations to submit grades.</div>`:''}<section class="panel"><div class="panel-title"><h2>${q.question_id}</h2><span class="badge">${queue.completed} / ${queue.total} submitted</span></div><p class="bengali" lang="bn">${escape(q.question_bn)}</p><div class="reference"><strong>Expected behavior · ${escape(q.expected_behavior)}</strong>${escape(q.ground_truth_answer??'No concrete answer; evaluate the specified behavior.')}</div><div class="reference"><strong>Source note</strong>${escape(q.source_note)}</div><div class="reference"><strong>Model answer · judge labels hidden</strong><span lang="bn">${escape(q.response_text)}</span></div><div class="divider"></div><form id="grade-form" class="grid-form">${identity()}<label class="wide">Correctness / expected behavior<select name="grade" required><option value="">Choose your grade…</option><option value="correct">Correct</option><option value="partial">Partial</option><option value="incorrect">Incorrect</option></select></label>${boolField('abstained','Did the model actually abstain?')}${boolField('behavior_met','Did it meet the expected behavior?')}${boolField('specific_unfounded','Did it make a specific unfounded assertion?')}${boolField('confident_language','Did the answer prose express explicit certainty?')}<label class="wide">Your rationale<textarea name="rationale" required maxlength="4000" placeholder="Explain your judgment using the reference and response."></textarea></label><label class="check wide"><input type="checkbox" required>I personally graded this response without consulting the machine judge’s labels.</label><div class="wide"><button class="primary" type="submit" ${local?'':'disabled'}>Save grade & next answer</button></div></form></section>`;
  }catch(error){$('#grading-detail').innerHTML=`<div class="empty">${escape(error.message)}</div>`;}
}

function renderJob(job){
  const el=$('#job');if(job.status==='idle'){el.hidden=true;return;}el.hidden=false;el.className='job-box';
  el.innerHTML=`<div class="panel-title"><strong>${escape(job.action||'Task')} · ${escape(job.status)}</strong>${job.status==='running'?'<button class="danger" data-action="stop">Stop task</button>':'<span>Local task log</span>'}</div><pre></pre>`;
  el.querySelector('pre').textContent=job.log||'Preparing task…';
}
document.addEventListener('click',async event=>{
  const el=event.target.closest('button');if(!el)return;
  try{
    if(el.dataset.view){state.view=el.dataset.view;await refresh();await render();return;}
    if(el.dataset.question){state.qid=el.dataset.question;questionList();questionDetail();return;}
    const action=el.dataset.action;if(!action)return;
    if(action==='refresh'){await refresh();await render();return;}
    if(action==='reload-grading'){await refresh();await grading();return;}
    el.disabled=true;
    const result=await api('/api/'+action,{run:el.dataset.run});
    if(result.run)state.run=result.run;
    notify(result.message||`${action==='stop'?'Task stopped':'Task started'}.`);
    await refresh();await render();
  }catch(error){notify(error.message,true);}finally{el.disabled=false;}
});
document.addEventListener('change',async event=>{
  const el=event.target;
  try{
    if(el.id==='dataset-choice'){state.dataset=el.value;state.qid=null;await dataset();}
    if(el.id==='category-filter'){state.category=el.value;questionList();}
    if(el.id==='report-choice'){state.report=el.value;await reportDetail();}
    if(['metric-model','metric-category'].includes(el.id))metrics();
    if(el.id==='grading-run'){state.run=el.value;await grading();}
    if(el.id==='run-provider')$('#run-model').value=defaults[el.value];
    if(el.id==='judge-provider')$('#judge-model').value=el.value==='gemini'?'gemini-3.5-flash':el.value==='groq'?defaults.groq:'';
  }catch(error){notify(error.message,true);}
});
document.addEventListener('input',event=>{if(event.target.id==='question-search'){state.query=event.target.value;questionList();}});
document.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target, data=Object.fromEntries(new FormData(form));const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
    let action;
    if(form.id==='review-form'){
      action='review';const q=state.questions.find(q=>q.id===state.qid);
      Object.assign(data,{dataset:state.dataset,question_id:q.id,question_sha256:q.question_sha256,native_bengali_speaker:data.native==='on',checks:{}});
      for(const key of ['natural_bengali','source_verified','premise_checked','behavior_appropriate'])data.checks[key]=data[key]==='true';
    }else if(form.id==='grade-form'){
      action='grade';const q=state.queue.rows[0];Object.assign(data,{run:state.run,question_id:q.question_id,response_sha256:q.response_sha256});
      for(const key of ['abstained','behavior_met','specific_unfounded','confident_language'])data[key]=data[key]==='true';
    }else{
      action=form.id==='run-form'?'generate':'judge';for(const key of ['interval','max_tokens','samples','limit'])if(key in data)data[key]=Number(data[key]);data.allow_unreviewed=data.allow_unreviewed==='on';
    }
    const result=await api('/api/'+action,data);notify(result.message||'Task started. Progress appears below.');
    if(action==='grade')await grading();else if(action==='review')form.reset();else{await refresh();runs();}
  }catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
setInterval(async()=>{
  if(polling||!state.data)return;polling=true;
  try{const job=await api('/api/job');renderJob(job);if(lastJobStatus==='running'&&job.status!=='running'){await refresh();if(state.view==='runs')runs();notify(job.status==='complete'?'Task completed. Refresh Results to inspect a generated report.':'Task stopped or failed. The actual error is preserved in the task log.',job.status==='failed');}lastJobStatus=job.status;}catch{}finally{polling=false;}
},2500);
(async()=>{try{await refresh();await render();}catch(error){$('#content').innerHTML=`<div class="empty">${escape(error.message)} Restart with python -m interface.server and refresh this page.</div>`;}})();
