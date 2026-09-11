'use strict';
const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const categories = {factual_high_certainty:'Factual · high certainty',factual_low_resource:'Bangladesh-specific',temporally_unstable:'Temporally unstable',ambiguous_contested:'Ambiguous / contested',unanswerable_adversarial:'Unanswerable / adversarial',code_switched:'Bengali–English mixed'};
const defaults = {gemini:'gemini-3.5-flash-lite',groq:'qwen/qwen3.8-27b',ollama:''};
const state = {view:'results',data:null,questions:[],qid:null,dataset:'dataset/draft-v0.1-batch01.jsonl',report:null,run:null,category:'',query:'',chart:'calibration',drafts:{},reviewerId:''};
let noticeTimer, polling=false, lastJobStatus;
const today = () => new Date().toLocaleDateString('en-CA');

function notify(message,error=false) {
  const el=$('#notice'); el.textContent=message; el.className=error?'error':''; el.hidden=false;
  clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>el.hidden=true,9000);
}
async function api(path,data) {
  const config=data?{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.data.token},body:JSON.stringify(data)}:{};
  const response=await fetch(path,config), value=await response.json();
  if(!response.ok) throw new Error(value.error||'Request failed.');
  return value;
}
function heading(title,description,action='') {
  return `<div class="page-heading"><div><h1>${title}</h1><p class="intro">${description}</p></div>${action}</div>`;
}
function options(values,selected) {
  return values.map(([v,t])=>`<option value="${escape(v)}" ${v===selected?'selected':''}>${escape(t)}</option>`).join('');
}
function boolField(name,label) {
  return `<fieldset><legend>${label}</legend><div class="choices"><label><input type="radio" name="${name}" value="true" required>Yes</label><label><input type="radio" name="${name}" value="false" required>No</label></div></fieldset>`;
}
function identity() {
  return `<label>Your name or reviewer ID<input name="reviewer_id" value="${escape(state.reviewerId)}" required maxlength="120" autocomplete="off"></label><label>Review date<input name="reviewed_at" type="date" value="${today()}" required></label>`;
}
function restoreForm(form,key) {
  form.dataset.draftKey=key;
  const saved=state.drafts[key]; if(!saved) return;
  for(const el of form.elements) {
    if(!el.name) continue;
    if(['checkbox','radio'].includes(el.type)) el.checked=(saved[el.name]||[]).includes(el.value);
    else if(saved[el.name]) el.value=saved[el.name][0];
  }
}
function rememberForm(form) {
  if(!form?.dataset.draftKey) return;
  const data=new FormData(form), saved={};
  for(const key of data.keys()) {
    if(form.id==='judge-form'&&key==='run')continue;
    saved[key]=data.getAll(key);
  }
  state.drafts[form.dataset.draftKey]=saved;
}
function artifact(file) { return `/artifact?report=${encodeURIComponent(state.report)}&file=${encodeURIComponent(file)}`; }
function metric(m) { return m?.estimate==null?'Unavailable':Number(m.estimate).toFixed(3); }
function interval(m) { return m?.ci95?m.ci95.map(v=>Number(v).toFixed(3)).join(' – '):'Unavailable'; }
async function refresh() { state.data=await api('/api/state');renderJob(state.data.job); }
async function render() {
  document.querySelectorAll('[data-view]').forEach(el=>{
    el.classList.toggle('active',el.dataset.view===state.view);
    el.setAttribute('aria-current',el.dataset.view===state.view?'page':'false');
  });
  if(state.view==='results') await results();
  if(state.view==='dataset') await dataset();
  if(state.view==='runs') runs();
  if(state.view==='grading') await grading();
}

async function results() {
  const d=state.data, archive=d.runs.filter(r=>!r.local), batch=d.datasets.find(x=>x.id==='dataset/draft-v0.1-batch01.jsonl');
  const count=archive.reduce((n,r)=>n+r.completed,0), judged=archive.reduce((n,r)=>n+r.judged,0);
  state.report=d.reports.includes(state.report)?state.report:d.reports[0];
  $('#content').innerHTML=heading('Results','Calibration, hallucination and human validation.','<div class="links" id="report-links"></div>')+`
    <div class="summary-line"><span><strong>${batch?.count??0}</strong> draft questions</span><span><strong>${count}</strong> archived answers</span><span><strong>${judged}/${count}</strong> machine graded</span></div>
    <div id="report-detail"></div>`;
  if(!d.reports.length) {
    $('#report-detail').innerHTML='<div class="empty">No reports yet. Generate one from a graded run in Evaluations.</div>';return;
  }
  await reportDetail();
}
async function reportDetail() {
  const report=await api('/api/report?report='+encodeURIComponent(state.report)); state.reportData=report;
  const models=[...new Set(Object.values(report.summaries).map(s=>`${s.provider}/${s.model}`))];
  const pending=report.inputs.reduce((n,i)=>n+i.n_ungraded,0);
  $('#report-links').innerHTML=['REPORT.md','metrics.csv','metrics.json'].map(f=>`<a href="${artifact(f)}" target="_blank" rel="noreferrer">${{'REPORT.md':'Full report','metrics.csv':'CSV','metrics.json':'JSON'}[f]}</a>`).join('');
  $('#report-detail').innerHTML=`
    <div class="callout"><strong>${escape(report.label)}</strong>${pending?`${pending} answers still need a machine grade. `:''}Check human validation below before drawing conclusions. These preview results do not establish a model ranking.</div>
    <div class="toolbar"><label>Report<select id="report-choice">${options(state.data.reports.map(p=>[p,p.replace('report/','')]),state.report)}</select></label><label>Model<select id="metric-model">${options(models.map(m=>[m,m]),models[0])}</select></label><label>Category<select id="metric-category"><option value="overall">All graded questions</option>${options(Object.entries(categories),'')}</select></label></div>
    <div id="metric-detail"></div>
    <section class="section"><div class="section-title"><h2>Charts · all models in this report</h2><span class="muted">${report.resamples.toLocaleString()} resamples · seed ${report.seed}</span></div>
      <div class="tabs" aria-label="Chart type"><button data-chart="calibration">Calibration</button><button data-chart="risk_coverage">Risk–coverage</button></div><div id="chart-detail"></div></section>
    <section class="section"><h2>Human validation</h2><div class="scroll"><table><thead><tr><th>Model</th><th>Human grades</th><th>Judge agreement · 95% CI</th><th>Status</th></tr></thead><tbody>
      ${report.inputs.map(i=>`<tr><td class="model">${escape(i.manifest.plan.config.model)}</td><td>${i.agreement.human_completed} / ${i.agreement.queue_size}</td><td>${metric(i.agreement.agreement.grade)}<br><span class="muted">${interval(i.agreement.agreement.grade)}</span></td><td class="status">${escape(i.agreement.status)}</td></tr>`).join('')}
    </tbody></table></div><p class="table-note">Agreement stays unavailable until humans have graded the validation sample.</p></section>`;
  metrics();chart();
}
function metrics() {
  const s=state.reportData.summaries[`${$('#metric-model').value}/${$('#metric-category').value}`];
  if(!s) { $('#metric-detail').innerHTML='<div class="empty">No graded answers in this category.</div>';return; }
  const fields=[['ece_confidence','Calibration error (ECE)'],['brier_confidence','Brier score'],['hallucination_rate','Hallucination rate'],['abstention_precision','Abstention precision'],['abstention_recall_category5','Abstention recall · unanswerable questions']];
  $('#metric-detail').innerHTML=`<div class="scroll"><table class="metrics-table"><thead><tr><th>Metric</th><th>Estimate</th><th>95% confidence interval</th></tr></thead><tbody>
    ${fields.map(([key,label])=>`<tr><td>${label}</td><td class="number estimate">${metric(s.metrics[key])}</td><td class="number">${interval(s.metrics[key])}</td></tr>`).join('')}
    </tbody></table></div><p class="table-note">${s.n_scored} graded answers · ${s.n_calibration} factual calibration items · ${s.n_hallucination_denominator} hallucination-test items.</p>
    <details class="table-note"><summary>How to read these numbers</summary><p>Values range from 0 to 1. Lower calibration error, Brier score and hallucination rates are better. Precision and recall measure different aspects of abstention. Small samples can produce misleadingly narrow intervals; read the full report’s limitations.</p></details>`;
}
function chart() {
  document.querySelectorAll('[data-chart]').forEach(b=>{b.classList.toggle('active',b.dataset.chart===state.chart);b.setAttribute('aria-pressed',b.dataset.chart===state.chart);});
  $('#chart-detail').innerHTML=`<img class="chart" src="${artifact(state.chart+'.png')}" alt="${state.chart==='calibration'?'Calibration diagram':'Risk–coverage curve with bootstrap intervals'} from the selected report">`;
}

function visibleQuestions() {
  return state.questions.filter(q=>(!state.category||q.category===state.category)&&`${q.id} ${q.question_bn} ${q.question_en_gloss}`.toLowerCase().includes(state.query.toLowerCase()));
}
async function dataset() {
  state.questions=await api('/api/questions?dataset='+encodeURIComponent(state.dataset));
  $('#content').innerHTML=heading('Questions','Check the question, verify its source, then record your independent review.')+`
    <div class="toolbar"><label>Dataset<select id="dataset-choice">${options(state.data.datasets.map(d=>[d.id,`${d.id.split('/').pop()} · ${d.count}`]),state.dataset)}</select></label>
    <label>Category<select id="category-filter"><option value="">All categories</option>${options(Object.entries(categories),state.category)}</select></label>
    <label class="search-label">Search<input id="question-search" type="search" value="${escape(state.query)}" placeholder="Question, English gloss or ID"></label></div>
    <div class="review-layout"><div><p id="question-count" class="muted"></p><div id="question-list" class="question-list" aria-label="Questions"></div></div><section id="question-detail" class="review-card"></section></div>`;
  questionList();questionDetail();
}
function questionList() {
  const rows=visibleQuestions();
  if(!rows.some(q=>q.id===state.qid)) {state.qid=rows[0]?.id;questionDetail();}
  $('#question-count').textContent=`${rows.length} question${rows.length===1?'':'s'}`;
  $('#question-list').innerHTML=rows.length?rows.map(q=>`<button data-question="${q.id}" class="${q.id===state.qid?'active':''}" aria-pressed="${q.id===state.qid}"><small>${q.id} · ${escape(q.difficulty_tier)}</small><span class="preview" lang="bn">${escape(q.question_bn)}</span></button>`).join(''):'<div class="empty">No matches. Try another search.</div>';
}
function questionDetail() {
  const q=state.questions.find(q=>q.id===state.qid);
  if(!q) {$('#question-detail').innerHTML='<div class="empty">Choose a question to review.</div>';return;}
  const rows=visibleQuestions(), index=rows.findIndex(item=>item.id===q.id);
  $('#question-detail').innerHTML=`<div class="panel-title"><span class="question-id">${q.id}</span><span class="status">${q.reviewed_by.length<2?'Awaiting human review':'Review IDs present'}</span></div>
    <p class="bengali" lang="bn">${escape(q.question_bn)}</p><p class="muted">${escape(q.question_en_gloss)}</p>
    <div class="reference"><strong>Expected: ${escape(q.expected_behavior.replaceAll('_',' '))}</strong>${escape(q.ground_truth_answer??'No concrete answer. Evaluate the specified behavior.')}</div>
    <div class="reference"><strong>Source / justification</strong>${escape(q.source_note)}</div>
    <details><summary>Category & construction notes</summary><p class="muted">${escape(categories[q.category])}</p><div class="reference">${escape(q.notes)}</div></details>
    <div class="divider"></div><h2>Your review</h2><p class="form-note">Your first decision is preserved. Other reviewers’ decisions stay hidden.</p>
    <form id="review-form" class="grid-form">${identity()}
      ${boolField('natural_bengali','Natural Bengali phrasing?')}${boolField('source_verified','Reference / source verified?')}${boolField('premise_checked','Factual or false premise justified?')}${boolField('behavior_appropriate','Expected behavior appropriate?')}
      <label class="wide">Decision<select name="decision" required><option value="">Select…</option><option value="accept">Accept</option><option value="revise">Needs revision</option><option value="reject">Reject</option></select></label>
      <label class="wide">Rationale and source evidence<textarea name="rationale" required maxlength="4000"></textarea></label>
      <label class="check wide"><input type="checkbox" name="native" required>I am a native Bengali speaker and personally performed this independent review.</label>
      <div class="form-actions wide"><button class="primary" type="submit">Save review & next</button><div class="row"><button class="secondary" type="button" data-step="-1" ${index===0?'disabled':''}>Previous</button><button class="secondary" type="button" data-step="1" ${index===rows.length-1?'disabled':''}>Next</button></div></div>
    </form>`;
  restoreForm($('#review-form'),`review:${state.dataset}:${q.question_sha256}`);
}
function nextQuestion(step=1) {
  const rows=visibleQuestions(), index=rows.findIndex(q=>q.id===state.qid);
  state.qid=rows[Math.max(0,Math.min(rows.length-1,index+step))]?.id;
  questionList();questionDetail();
}

function runOptions(local=false) {
  return state.data.runs.filter(r=>!local||r.local).map(r=>[r.id,`${r.config.model} · ${r.id.split('/').pop()}${r.local?'':' (archive)'}`]);
}
function runs() {
  $('#content').innerHTML=heading('Evaluations','Run a model, grade its answers, then generate a report.','<button class="primary" data-open="generate">New evaluation</button>')+`
    <div class="section-title"><span class="muted">${state.data.runs.length} saved runs</span><button class="text-button" data-action="refresh">Refresh</button></div>
    <div class="scroll"><table><thead><tr><th>Model / run</th><th>Answers</th><th>Machine grades</th><th>Human grades</th><th>Actions</th></tr></thead><tbody>
    ${state.data.runs.map(r=>`<tr><td class="model">${escape(r.config.model)}<small>${escape(r.id.split('/').pop())} · ${r.local?'local': 'read-only archive'} · ${escape(r.status)}</small></td><td>${r.completed}/${r.planned}</td><td>${r.judged}/${r.completed}</td><td>${r.human}</td>
    <td class="run-actions">${r.local?`<div class="row"><button class="secondary" data-open="judge" data-run="${escape(r.id)}">Judge answers</button><button class="text-button" data-grade="${escape(r.id)}">Human grading</button></div>
      <details class="run-menu"><summary>More actions</summary><div class="menu-items"><button class="text-button" data-action="resume" data-run="${escape(r.id)}">Resume generation</button><button class="text-button" data-action="assess" data-run="${escape(r.id)}">Prepare / assess human queue</button><button class="text-button" data-action="report" data-run="${escape(r.id)}">Generate report</button><button class="text-button" data-action="expand" data-run="${escape(r.id)}">Expand queue after low agreement</button></div></details>`:
      `<button class="secondary" data-action="clone" data-run="${escape(r.id)}">Make local copy</button>`}</td></tr>`).join('')}
    </tbody></table></div><p class="table-note">Archived evidence is read-only. Make a local copy to continue its grading or generate a new report.</p>`;
}
function providerFields(config) {
  return `<label>Provider<select name="provider" id="provider-choice">${options([['gemini','Gemini · free tier'],['groq','Groq · free tier'],['ollama','Ollama · local']],config.provider)}</select></label>
    <label>Model ID<input name="model" id="model-choice" value="${escape(config.model)}" required maxlength="160" placeholder="Installed or available model ID"></label>`;
}
function openTask(action,runId) {
  const judge=action==='judge', run=state.data.runs.find(r=>r.id===runId);
  const config=run?.judge_config||{provider:'gemini',model:judge?'gemini-3.5-flash':defaults.gemini};
  const dialog=$('#task-dialog');
  dialog.innerHTML=`<div class="dialog-heading"><h2 id="dialog-title">${judge?'Judge answers':'New evaluation'}</h2><button data-close aria-label="Close form">×</button></div>
    <p class="form-note">${judge?'Use a different model from the one being evaluated. Human validation follows this initial grading pass.':'New runs are saved locally. Choose a free-tier provider or an installed Ollama model.'}</p>
    <form id="${judge?'judge':'run'}-form" class="grid-form">
    ${judge?`<label class="wide">Run<select name="run" id="judge-run" required>${options(runOptions(true),runId)}</select></label>`:
      `<label class="wide">Run name<input name="name" required pattern="[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}" placeholder="bengali-pilot-01"></label><label class="wide">Dataset<select name="dataset" id="run-dataset">${options(state.data.datasets.map(d=>[d.id,d.id.split('/').pop()]),state.dataset)}</select></label>`}
    ${providerFields(config)}
    ${judge?'':`<label>Questions<input name="limit" type="number" min="1" value="24" required></label><label>Samples per question<input name="samples" type="number" min="2" max="10" value="3" required></label><p id="request-count" class="form-note wide"></p><label class="check wide"><input type="checkbox" name="allow_unreviewed">Allow draft questions. Outputs will be labeled PRELIMINARY, UNREVIEWED DATA.</label>`}
    <details class="advanced wide"><summary>Advanced settings</summary><div class="grid-form"><label>Seconds between requests<input name="interval" type="number" value="${config.interval_seconds??6}" min="0" max="3600" required></label><label>Maximum output tokens<input name="max_tokens" type="number" value="${config.max_tokens??1024}" min="128" max="8192" required></label></div></details>
    <p id="provider-status" class="form-note wide"></p><label class="check wide"><input type="checkbox" name="attestation" required>I am using free-tier access with billing disabled, or a local model.</label>
    <div class="form-actions wide"><button class="secondary" type="button" data-close>Cancel</button><button class="primary" type="submit">${judge?'Start / resume judging':'Start evaluation'}</button></div></form>`;
  restoreForm(dialog.querySelector('form'),judge?`judge:${runId}`:'new-run');
  updateProvider();if(!judge)updateRequestCount(true);dialog.showModal();
  dialog.querySelector('input:not([type="checkbox"])')?.focus();
}
function updateProvider() {
  const provider=$('#provider-choice').value;
  $('#provider-status').textContent=provider==='ollama'?'Ollama must be running locally.':`${provider==='gemini'?'Gemini':'Groq'} key ${state.data.credentials[provider]?'configured':'missing — set it in .env and restart'}. Free quotas still apply.`;
}
function updateRequestCount(clamp=false) {
  const form=$('#run-form');if(!form)return;
  const d=state.data.datasets.find(d=>d.id===form.elements.dataset.value), limit=form.elements.limit;
  limit.max=d.eligible??d.count;
  if(clamp)limit.value=Math.min(Number(limit.value),Number(limit.max));
  $('#request-count').textContent=`${Number(limit.value)*(1+Number(form.elements.samples.value))} generation requests. ${limit.max} questions available after pilot exclusions. Full evaluations normally use 10 samples.`;
}

async function grading() {
  const choices=runOptions();
  if(!choices.some(([id])=>id===state.run))state.run=choices.find(([id])=>id.startsWith('results/local/'))?.[0]||choices[0]?.[0];
  $('#content').innerHTML=heading('Human grading','Judge the answer against its reference. Machine grades stay hidden.')+`
    <div class="toolbar"><label>Run<select id="grading-run">${options(choices,state.run)}</select></label><button class="secondary" data-action="reload-grading">Refresh queue</button></div><div id="grading-detail"></div>`;
  if(!state.run){$('#grading-detail').innerHTML='<div class="empty">Start an evaluation, then prepare its human queue.</div>';return;}
  try {
    const queue=await api('/api/queue?run='+encodeURIComponent(state.run));state.queue=queue;
    const local=state.data.runs.find(r=>r.id===state.run)?.local, q=queue.rows[0];
    if(!q){$('#grading-detail').innerHTML=`<div class="empty"><h2>All queued answers have a human grade.</h2><p>${queue.completed} submitted. Calculate agreement to check for unresolved disagreements.</p>${local?`<button class="primary" data-action="assess" data-run="${escape(state.run)}">Calculate agreement</button>`:''}</div>`;return;}
    $('#grading-detail').innerHTML=`${!local?'<div class="callout">This archive is read-only. Make a local copy in Evaluations to submit grades.</div>':''}
      <div class="panel-title"><span class="question-id">${q.question_id}</span><span class="status">${queue.completed} of ${queue.total} submitted</span></div>
      <p class="bengali" lang="bn">${escape(q.question_bn)}</p><div class="reference"><strong>Expected: ${escape(q.expected_behavior.replaceAll('_',' '))}</strong>${escape(q.ground_truth_answer??'No concrete answer. Evaluate the specified behavior.')}</div>
      <details><summary>Reference source</summary><div class="reference">${escape(q.source_note)}</div></details><div class="reference"><strong>Model answer · machine grade hidden</strong><span lang="bn">${escape(q.response_text)}</span></div>
      <div class="divider"></div><h2>Your grade</h2><form id="grade-form" class="grid-form">${identity()}
      <label class="wide">Correctness / expected behavior<select name="grade" required><option value="">Select…</option><option value="correct">Correct</option><option value="partial">Partial</option><option value="incorrect">Incorrect</option></select></label>
      ${boolField('abstained','Did the model actually abstain?')}${boolField('behavior_met','Did it meet the expected behavior?')}${boolField('specific_unfounded','Did it make a specific unfounded assertion?')}${boolField('confident_language','Did its prose express explicit certainty?')}
      <label class="wide">Rationale<textarea name="rationale" required maxlength="4000"></textarea></label><label class="check wide"><input type="checkbox" name="attestation" required>I personally graded this response without consulting the machine judge’s labels.</label>
      <div class="wide"><button class="primary" type="submit" ${local?'':'disabled'}>Save grade & next</button></div></form>`;
    restoreForm($('#grade-form'),`grade:${state.run}:${q.response_sha256}`);
  }catch(error){$('#grading-detail').innerHTML=`<div class="empty">${escape(error.message)}<p>Use “Prepare / assess human queue” under the run’s More actions.</p></div>`;}
}

function renderJob(job) {
  const el=$('#job');if(job.status==='idle'){el.hidden=true;return;}
  el.hidden=false;el.className='job-box';
  const wasOpen=el.querySelector('details')?.open;
  el.innerHTML=`<details ${job.status==='running'||wasOpen?'open':''}><summary>Last task: ${escape(job.action||'task')} · ${escape(job.status)}</summary><div class="panel-title"><span>Saved task log</span>${job.status==='running'?'<button class="danger" data-action="stop">Stop task</button>':''}</div><pre></pre></details>`;
  el.querySelector('pre').textContent=job.log||'Preparing task…';
}
document.addEventListener('click',async event=>{
  const el=event.target.closest('button');if(!el)return;
  try {
    if(el.hasAttribute('data-close')){$('#task-dialog').close();return;}
    if(el.dataset.open){openTask(el.dataset.open,el.dataset.run);return;}
    if(el.dataset.chart){state.chart=el.dataset.chart;chart();return;}
    if(el.dataset.view||el.dataset.grade){state.view=el.dataset.grade?'grading':el.dataset.view;if(el.dataset.grade)state.run=el.dataset.grade;await refresh();await render();return;}
    if(el.dataset.question){state.qid=el.dataset.question;questionList();questionDetail();return;}
    if(el.dataset.step){nextQuestion(Number(el.dataset.step));return;}
    const action=el.dataset.action;if(!action)return;
    if(action==='refresh'||action==='reload-grading'){await refresh();await render();return;}
    el.disabled=true;const result=await api('/api/'+action,{run:el.dataset.run});
    if(result.run)state.run=result.run;
    notify(result.message||(action==='stop'?'Task stopped.':'Task started. Progress is below.'));
    await refresh();await render();
  }catch(error){notify(error.message,true);}finally{el.disabled=false;}
});
document.addEventListener('change',async event=>{
  const el=event.target;rememberForm(el.form);
  try {
    if(el.id==='dataset-choice'){state.dataset=el.value;state.qid=null;await dataset();}
    if(el.id==='category-filter'){state.category=el.value;questionList();}
    if(el.id==='report-choice'){state.report=el.value;await reportDetail();}
    if(['metric-model','metric-category'].includes(el.id))metrics();
    if(el.id==='grading-run'){state.run=el.value;await grading();}
    if(el.id==='provider-choice'){$('#model-choice').value=el.form.id==='judge-form'&&el.value==='gemini'?'gemini-3.5-flash':defaults[el.value];updateProvider();rememberForm(el.form);}
    if(el.id==='judge-run'){$('#task-dialog').close();openTask('judge',el.value);}
    if(el.id==='run-dataset')updateRequestCount(true);
  }catch(error){notify(error.message,true);}
});
document.addEventListener('input',event=>{
  if(event.target.name==='reviewer_id')state.reviewerId=event.target.value;
  rememberForm(event.target.form);
  if(event.target.id==='question-search'){state.query=event.target.value;questionList();}
  if(event.target.form?.id==='run-form')updateRequestCount();
});
document.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target,data=Object.fromEntries(new FormData(form)),button=form.querySelector('button[type=submit]');button.disabled=true;
  try {
    let action;
    if(form.id==='review-form') {
      action='review';const q=state.questions.find(q=>q.id===state.qid);
      Object.assign(data,{dataset:state.dataset,question_id:q.id,question_sha256:q.question_sha256,native_bengali_speaker:data.native==='on',checks:{}});
      for(const key of ['natural_bengali','source_verified','premise_checked','behavior_appropriate'])data.checks[key]=data[key]==='true';
    }else if(form.id==='grade-form') {
      action='grade';const q=state.queue.rows[0];Object.assign(data,{run:state.run,question_id:q.question_id,response_sha256:q.response_sha256});
      for(const key of ['abstained','behavior_met','specific_unfounded','confident_language'])data[key]=data[key]==='true';
    }else {
      action=form.id==='run-form'?'generate':'judge';
      for(const key of ['interval','max_tokens','samples','limit'])if(key in data)data[key]=Number(data[key]);
      data.allow_unreviewed=data.allow_unreviewed==='on';
    }
    const result=await api('/api/'+action,data);delete state.drafts[form.dataset.draftKey];notify(result.message||'Task started. Progress is below.');
    if(action==='grade')await grading();
    else if(action==='review')nextQuestion();
    else{$('#task-dialog').close();await refresh();runs();}
  }catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
// Native validation must be visible even when a user enters invalid advanced values.
document.addEventListener('invalid',event=>{event.target.closest('details')?.setAttribute('open','');},true);
setInterval(async()=>{
  if(polling||!state.data)return;polling=true;
  try {
    const job=await api('/api/job');renderJob(job);
    if(lastJobStatus==='running'&&job.status!=='running'){
      await refresh();if(state.view==='runs'&&!$('#task-dialog').open)runs();
      notify(job.status==='complete'?'Task completed. New reports are available in Results.':'Task stopped or failed. See the task log for details.',job.status==='failed');
    }
    lastJobStatus=job.status;
  }catch{}finally{polling=false;}
},2500);
(async()=>{try{await refresh();await render();}catch(error){$('#content').innerHTML=`<div class="empty">${escape(error.message)} Restart with python -m interface.server and refresh.</div>`;}})();
