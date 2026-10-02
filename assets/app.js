(function(){
  const $=s=>document.querySelector(s);
  const LABEL={lawsuit:'Court Docket',regulator:'Regulators',news:'Reporting',tenant:'Letters from Tenants'};
  const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const st={cat:'all',q:'',loc:'',sort:'desc'};
  try{Object.assign(st,JSON.parse(sessionStorage.getItem('gsr-filters')||'{}'))}catch(e){}
  let all=[];

  function fmtDate(d){
    const p=(d||'').split('-');
    const m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    if(p.length===3)return `${m[+p[1]-1]} ${+p[2]}, ${p[0]}`;
    if(p.length===2)return `${m[+p[1]-1]} ${p[0]}`;
    return p[0]||'Undated';
  }
  function match(e){
    if(st.cat==='bf'){if(!(e.subject||[]).includes('bob-faith'))return false}
    else if(st.cat!=='all'&&e.category!==st.cat)return false;
    if(st.loc&&e.location!==st.loc)return false;
    if(st.q){
      const hay=[e.title,e.summary,e.property,e.location,e.outlet,e.status].join(' ').toLowerCase();
      if(!st.q.toLowerCase().split(/\s+/).every(w=>hay.includes(w)))return false;
    }
    return true;
  }
  function render(){
    try{sessionStorage.setItem('gsr-filters',JSON.stringify(st))}catch(e){}
    const rows=all.filter(match).sort((a,b)=>st.sort==='desc'?b.date.localeCompare(a.date):a.date.localeCompare(b.date));
    let html='<div class="grid">',yr=null;
    for(const e of rows){
      const y=(e.date||'').slice(0,4)||'Undated';
      if(y!==yr){html+=`<div class="year">${esc(y)}</div>`;yr=y}
      const bf=(e.subject||[]).includes('bob-faith')?' · The Chairman':'';
      html+=`<article class="entry ${esc(e.category)}" id="${esc(e.id)}">
          <p class="kicker">${esc(LABEL[e.category]||e.category)}${bf}</p>
          <h2><a href="${esc(e.url)}" rel="noopener" target="_blank">${esc(e.title)}</a></h2>
          <p>${esc(e.summary)}</p>
          ${e.status?`<div class="status">${esc(e.status)}</div>`:''}
          <div class="byline">${esc([fmtDate(e.date),e.outlet,e.property,e.location].filter(Boolean).join(' · '))}</div>
          <div class="src"><a href="${esc(e.url)}" rel="noopener" target="_blank">Source</a>${e.archive_url?`<a href="${esc(e.archive_url)}" rel="noopener" target="_blank">Archive</a>`:''}<a href="#${esc(e.id)}">Permalink</a></div>
        </article>`;
    }
    $('#ledger').innerHTML=rows.length?html+'</div>':'<p class="empty">Nothing in the archive matches.</p>';
  }
  function tally(){
    const c=k=>k==='bf'?all.filter(e=>(e.subject||[]).includes('bob-faith')).length:all.filter(e=>e.category===k).length;
    const now=new Date();
    $('#issue').textContent=`Vol. I · ${now.toLocaleString('en-US',{month:'long',year:'numeric'})}`;
    $('#count').textContent=`${all.length} stories on record`;
    const lead=all.find(e=>e.featured)||all.filter(e=>e.category==='regulator'||e.category==='lawsuit').sort((a,b)=>b.date.localeCompare(a.date))[0];
    if(lead){
      $('#cover').innerHTML=`<div>
        <p class="kicker">Cover Story · ${esc(LABEL[lead.category])}</p>
        <h2><a href="${esc(lead.url)}" rel="noopener" target="_blank">${esc(lead.title)}</a></h2>
        <p class="dek">${esc(lead.summary)}</p>
        <p class="byline">${esc([fmtDate(lead.date),lead.outlet,lead.status].filter(Boolean).join(' · '))}</p></div>
        <aside class="contents"><h3>In This Issue</h3>${[['lawsuit','Court Docket'],['regulator','Regulators'],['news','Reporting'],['tenant','Letters from Tenants'],['bf','The Chairman']]
          .map(([k,l])=>`<button data-cat="${k}">${l}<b>${c(k)}</b></button>`).join('')}</aside>`;
    }
    const locs=[...new Set(all.map(e=>e.location).filter(Boolean))].sort();
    $('#loc').innerHTML='<option value="">All locations</option>'+locs.map(l=>`<option>${esc(l)}</option>`).join('');
  }
  function sync(){
    document.querySelectorAll('#cats button').forEach(b=>b.classList.toggle('on',b.dataset.cat===st.cat));
    $('#q').value=st.q;$('#loc').value=st.loc;$('#sort').value=st.sort;
  }
  const pick=e=>{const b=e.target.closest('button[data-cat]');if(!b)return;st.cat=b.dataset.cat;sync();render();
    if(e.currentTarget.id==='cover')document.querySelector('.toolbar').scrollIntoView({behavior:'smooth'})};
  $('#cats').addEventListener('click',pick);$('#cover').addEventListener('click',pick);
  $('#q').addEventListener('input',e=>{st.q=e.target.value.trim();render()});
  $('#loc').addEventListener('change',e=>{st.loc=e.target.value;render()});
  $('#sort').addEventListener('change',e=>{st.sort=e.target.value;render()});
  // ---- Property directory (footer) ----
  const STATES={AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',CO:'Colorado',CT:'Connecticut',DE:'Delaware',DC:'District of Columbia',FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming'};
  let props=[];
  function cityBlocks(list){
    const by={};list.forEach(p=>(by[p.c]=by[p.c]||[]).push(p));
    return Object.keys(by).sort().map(c=>`<div class="city"><b>${esc(c)}</b>${by[c].map(p=>
      `<a href="#" data-p="${esc(p.n)}">${esc(p.n)}</a><a class="gs" href="https://www.greystar.com/${esc(p.slug)}/p_${esc(p.id)}" rel="noopener" target="_blank" title="Greystar listing">↗</a>`).join(' ')}</div>`).join('');
  }
  function renderProps(){
    const q=$('#pq').value.trim().toLowerCase();
    const list=q?props.filter(p=>(p.n+' '+p.c+' '+(STATES[p.s]||p.s)).toLowerCase().includes(q)):props;
    const groups={};list.forEach(p=>(groups[p.s]=groups[p.s]||[]).push(p));
    const name=s=>STATES[s]||s;
    const keys=Object.keys(groups).sort((a,b)=>(a.length===2?0:1)-(b.length===2?0:1)||name(a).localeCompare(name(b)));
    $('#props').innerHTML=keys.map(k=>`<details data-s="${esc(k)}"${q&&list.length<300?' open':''}><summary>${esc(name(k))} <span>(${groups[k].length})</span></summary>${q&&list.length<300?cityBlocks(groups[k]):''}</details>`).join('')||'<p class="empty">No matching property.</p>';
    $('#props').querySelectorAll('details').forEach(d=>d.addEventListener('toggle',()=>{if(d.open&&!d.children[1])d.insertAdjacentHTML('beforeend',cityBlocks(groups[d.dataset.s]))}));
  }
  $('#pq').addEventListener('input',renderProps);
  $('#props').addEventListener('click',e=>{const a=e.target.closest('a[data-p]');if(!a)return;e.preventDefault();
    st.q=a.dataset.p;st.cat='all';st.loc='';sync();render();window.scrollTo({top:0,behavior:'smooth'})});
  fetch('data/properties.json').then(r=>r.json()).then(d=>{props=d;$('#props-n').textContent=d.length.toLocaleString();renderProps()}).catch(()=>{});

  fetch('data/entries.json',{cache:'no-cache'}).then(r=>r.json()).then(d=>{all=d;tally();sync();render();
    if(location.hash){const el=document.getElementById(location.hash.slice(1));if(el)el.scrollIntoView()}})
    .catch(()=>{$('#ledger').innerHTML='<p class="empty">Could not load the record.</p>'});
})();
