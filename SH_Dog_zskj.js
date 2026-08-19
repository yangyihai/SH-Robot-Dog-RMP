/* ===== DATA ===== */
const AVCL=['#3b82f6','#8b5cf6','#ec4899','#f59e0b','#10b981','#06b6d4','#f43f5e','#6366f1'];
function avC(s){let h=0;for(let i=0;i<s.length;i++)h=s.charCodeAt(i)+((h<<5)-h);return AVCL[Math.abs(h)%AVCL.length]}

/* ===== STATE ===== */
let DEVS=[];                       // 设备清单（来自服务端）
let checkouts={},reserves={},pendings={},hist=[];
let user={name:'',dept:'研发'};     // 个人信息保留在本地浏览器
let curPage=0,filter='all';
let retId=null,rvId=null,clId=null,bkId=null,edId=null,delId=null;

/* ===== USER (本地) ===== */
function loadUser(){try{const u=localStorage.getItem('dm_user');if(u)user=JSON.parse(u)}catch(e){}}
function saveUser(){localStorage.setItem('dm_user',JSON.stringify(user));}

/* ===== API ===== */
async function api(url,body){
  const opt={method:body?'POST':'GET',headers:{'Content-Type':'application/json'}};
  if(body)opt.body=JSON.stringify(body);
  const res=await fetch(url,opt);
  if(!res.ok){
    const e=await res.json().catch(()=>({}));
    throw new Error(e.error||'请求失败');
  }
  return res.json();
}
async function refresh(){
  const s=await api('/api/state');
  DEVS=s.devices||[];
  checkouts=s.checkouts||{};
  reserves=s.reserves||{};
  pendings=s.pendings||{};
  hist=s.hist||[];
  renderDevices();renderHist();          // renderDevices 内部已调用 renderHero
}

/* ===== HELPERS ===== */
function fDur(ms){if(ms<0)ms=0;const m=Math.floor(ms/60000);if(m<60)return m+'分钟';const h=Math.floor(m/60);const r=m%60;if(h<24)return r?h+'时'+r+'分':h+'小时';const d=Math.floor(h/24);const rh=h%24;return rh?d+'天'+rh+'时':d+'天'}
function fT(iso){const d=new Date(iso),p=n=>String(n).padStart(2,'0');return`${d.getMonth()+1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`}
function fTF(iso){const d=new Date(iso),p=n=>String(n).padStart(2,'0');return`${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`}
function isOver(id){const c=checkouts[id];return c?new Date()>new Date(c.expectedReturn):false}

/* ===== SLIDE NAV ===== */
function goTo(n){
  curPage=Math.max(0,Math.min(n,2));
  document.getElementById('track').style.transform=`translateX(-${curPage*100}vw)`;
  updateSlideUI();
}
function next(){if(curPage<2)goTo(curPage+1)}
function prev(){if(curPage>0)goTo(curPage-1)}

function updateSlideUI(){
  const dark=curPage===0;
  document.getElementById('nav').classList.toggle('light',!dark);
  document.getElementById('arrL').className='arrow arrow-l '+(dark?'dark':'light');
  document.getElementById('arrR').className='arrow arrow-r '+(dark?'dark':'light');
  document.getElementById('arrL').disabled=curPage===0;
  document.getElementById('arrR').disabled=curPage===2;
}

/* ===== TOUCH — 只允许向左滑（前进到下一页） ===== */
let tX0=0,tY0=0,tMoved=false,tLocked=false;
const pager=document.getElementById('pager');
const track=document.getElementById('track');

pager.addEventListener('touchstart',e=>{
  tX0=e.touches[0].clientX;
  tY0=e.touches[0].clientY;
  tMoved=false;
  tLocked=false;
},{passive:true});

pager.addEventListener('touchmove',e=>{
  if(tLocked)return;
  const dx=e.touches[0].clientX-tX0;
  const dy=e.touches[0].clientY-tY0;

  if(!tMoved){
    if(Math.abs(dy)>Math.abs(dx)){tLocked=true;return}
    if(Math.abs(dx)>12){
      // 只允许向左滑（dx < 0），即前进到下一页
      if(dx>0){tLocked=true;return}
      tMoved=true;
      track.style.transition='none';
    }
  }

  if(tMoved){
    e.preventDefault();
    const maxDx=0;
    const minDx=-(2-curPage)*window.innerWidth;
    const clamped=Math.max(minDx,Math.min(maxDx,dx));
    track.style.transform=`translateX(calc(-${curPage*100}vw + ${clamped}px))`;
  }
},{passive:false});

pager.addEventListener('touchend',e=>{
  track.style.transition='';
  if(!tMoved){tMoved=false;return}
  const dx=e.changedTouches[0].clientX-tX0;
  if(dx<-60&&curPage<2){goTo(curPage+1)}else{goTo(curPage)}
  tMoved=false;
});

/* ===== RENDER HERO ===== */
function renderHero(){
  const total=DEVS.length;let use=0,pn=0,broken=0;
  for(const id in checkouts)use++;
  for(const id in pendings)pn++;
  DEVS.forEach(d=>{if(d.status==='broken')broken++});
  document.getElementById('sTotal').textContent=total;
  document.getElementById('sAvail').textContent=total-use-pn-broken;
  document.getElementById('sUse').textContent=use;
  document.getElementById('sPend').textContent=pn;
}

/* ===== RENDER DEVICES ===== */
function renderDevices(){
  const q=(document.getElementById('searchBox').value||'').toLowerCase().trim();
  const myName=user.name,myDept=user.dept;
  let html='',cAvail=0,cUse=0,cPend=0,cBroken=0;
  DEVS.forEach((d,i)=>{
    const c=checkouts[d.id],pn=pendings[d.id],rv=reserves[d.id]||[];
    const broken=d.status==='broken';
    // 匹配必须姓名+部门同时一致，不能只按姓名或只按部门
    const myQ=rv.findIndex(r=>r.user===myName&&r.dept===myDept);
    const overdue=c&&isOver(d.id);
    let st,sCls;
    if(broken){st='故障';sCls='broken';cBroken++}
    else if(pn){st='待领取';sCls='pend';cPend++}
    else if(c){st=overdue?'超时':'使用中';sCls=overdue?'over':'use';cUse++}
    else{st='空闲';sCls='avail';cAvail++}

    if(filter==='available'&&sCls!=='avail')return;
    if(filter==='in-use'&&sCls!=='use'&&sCls!=='over')return;
    if(filter==='pending'&&sCls!=='pend')return;
    if(filter==='broken'&&sCls!=='broken')return;

    if(q){
      const hay=[d.name,d.series,d.sn,d.brokenNote,c?.user,c?.dept,pn?.user,pn?.dept,...(rv.map(r=>r.user)),...(rv.map(r=>r.dept))].filter(Boolean).join(' ').toLowerCase();
      if(!hay.includes(q))return;
    }

    let userHtml='—',purposeHtml='—';
    if(broken){
      purposeHtml=d.brokenNote?`<span style="color:var(--c-t2)">${d.brokenNote}</span>`:'—';
    }else if(pn){
      const cl=avC(pn.user);
      userHtml=`<div class="td-user"><div class="avatar" style="background:${cl}18;color:${cl}">${pn.user[0]}</div><span>${pn.user}<span style="font-size:11px;color:var(--c-t3);margin-left:3px">${pn.dept}</span></span></div>`;
      purposeHtml=pn.purpose||'—';
    }else if(c){
      const cl=avC(c.user);
      userHtml=`<div class="td-user"><div class="avatar" style="background:${cl}18;color:${cl}">${c.user[0]}</div><span>${c.user}<span style="font-size:11px;color:var(--c-t3);margin-left:3px">${c.dept}</span></span></div>`;
      purposeHtml=c.purpose||'—';
    }

    let actHtml='';
    if(broken){
      actHtml=`<button class="a-link" onclick="repairDev('${d.id}')">恢复</button>`;
    }else if(pn){
      if(pn.user===myName&&pn.dept===myDept){
        actHtml=`<button class="a-link" onclick="openCL('${d.id}')">领取</button><button class="a-link subtle" onclick="declineCLDirect('${d.id}')">跳过</button>`;
      }else{
        if(myQ<0)actHtml=`<button class="a-link subtle" onclick="openRV('${d.id}')">预约排队</button>`;
        else actHtml=`<button class="a-link subtle" onclick="cancelRV('${d.id}')">取消预约 · 第${myQ+1}位</button>`;
      }
    }else if(c){
      if(c.user===myName&&c.dept===myDept){
        actHtml=`<button class="a-link danger" onclick="openRT('${d.id}')">归还</button>`;
      }else{
        if(myQ<0)actHtml=`<button class="a-link" onclick="openRV('${d.id}')">预约</button>`;
        else actHtml=`<button class="a-link subtle" onclick="cancelRV('${d.id}')">已预约 · 第${myQ+1}位</button>`;
      }
    }else{
      actHtml=`<button class="a-link" onclick="openCOFor('${d.id}')">领用</button>`;
    }

    // 管理操作：仅"测试"部门可见编辑/删除；报修仅空闲；删除仅空闲或故障（无进行中占用）
    const isTest=myDept==='测试';
    let mgmt='';
    if(isTest){
      mgmt+=`<button class="a-link subtle" onclick="openEditDevice('${d.id}')">编辑</button>`;
      if(sCls==='avail'||sCls==='broken')mgmt+=`<button class="a-link subtle" onclick="openDelDevice('${d.id}')">删除</button>`;
    }
    if(sCls==='avail')mgmt+=`<button class="a-link subtle" onclick="openBroken('${d.id}')">报修</button>`;
    actHtml+=mgmt;

    const pillClass=sCls==='avail'?'green':sCls==='pend'?'purple':sCls==='over'?'red':sCls==='broken'?'broken':'orange';
    const qBadge=rv.length?`<span class="pill pill-orange" style="margin-left:6px">${rv.length}人预约</span>`:
                  pn?`<span class="pill pill-purple" style="margin-left:6px">待领取</span>`:'';

    html+=`<tr>
      <td><span class="dot-s ${sCls}"></span></td>
      <td><div class="td-dev">${d.name}</div><div class="td-sn">${d.sn}</div></td>
      <td class="td-series">${d.series}</td>
      <td><span class="pill pill-${pillClass}">${st}</span></td>
      <td>${userHtml}</td>
      <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${purposeHtml}</td>
      <td><div class="act">${actHtml}${qBadge}</div></td>
    </tr>`;
  });

  if(!html)html=`<tr><td colspan="7" class="empty">没有匹配的设备</td></tr>`;
  const twrap=document.querySelector('.t-wrap');
  const tScroll=twrap?twrap.scrollTop:0;               // 自动刷新时保留滚动位置
  document.getElementById('devBody').innerHTML=html;
  if(twrap)twrap.scrollTop=tScroll;
  const total=DEVS.length;
  document.getElementById('devFoot').innerHTML=`<span>共 <b>${total}</b> 台</span><span><b>${cAvail}</b> 空闲</span><span><b>${cUse}</b> 使用中</span><span><b>${cPend}</b> 待领取</span>`+(cBroken?`<span><b>${cBroken}</b> 故障</span>`:'');
  renderHero();
}

/* ===== RENDER HISTORY ===== */
function renderHist(){
  const body=document.getElementById('histBody');
  const hwrap=document.querySelector('.h-wrap');
  const hScroll=hwrap?hwrap.scrollTop:0;               // 自动刷新时保留滚动位置
  if(!hist.length){body.innerHTML='<tr><td colspan="6" class="empty">暂无使用记录</td></tr>';if(hwrap)hwrap.scrollTop=hScroll;return}
  let h='';[...hist].reverse().forEach(r=>{
    const dur=fDur(new Date(r.returnTime)-new Date(r.checkoutTime));
    h+=`<tr>
      <td style="font-weight:600">${r.deviceName}</td>
      <td>${r.user}<span style="color:var(--c-t3);font-size:11px;margin-left:3px">${r.dept}</span></td>
      <td><span class="pill pill-gray">${r.purpose||'—'}</span></td>
      <td class="mono">${fT(r.checkoutTime)}</td>
      <td class="mono">${fT(r.returnTime)}</td>
      <td><span class="pill pill-gray">${dur}</span></td>
    </tr>`;
  });
  body.innerHTML=h;
  if(hwrap)hwrap.scrollTop=hScroll;
}

/* ===== FILTER ===== */
function setF(f,el){
  filter=f;
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));
  el.classList.add('on');
  renderDevices();
}

/* ===== USER SETUP ===== */
// 个人信息（姓名+部门）绑定为单一身份；允许修改，但当前身份下存在在用/预约/待领取设备时禁止修改
function hasActiveRecords(){
  const n=user.name,dp=user.dept;
  for(const id in checkouts){const c=checkouts[id];if(c.user===n&&c.dept===dp)return true}
  for(const id in pendings){const p=pendings[id];if(p.user===n&&p.dept===dp)return true}
  for(const id in reserves){if((reserves[id]||[]).some(r=>r.user===n&&r.dept===dp))return true}
  return false;
}
function openSetup(edit){
  document.getElementById('setupTitle').textContent=edit?'修改个人信息':'欢迎使用';
  document.getElementById('fSName').value=user.name;
  document.getElementById('fSDept').value=user.dept;
  openM('mSetup');
  setTimeout(()=>document.getElementById('fSName').focus(),100);
}
function onNavUser(){
  // 允许修改个人信息（姓名+部门仍作为绑定身份）
  openSetup(true);
}
function confirmSetup(){
  const name=document.getElementById('fSName').value.trim();
  if(!name){toast('请输入姓名');return}
  if(!/^[\u4e00-\u9fa5a-zA-Z·.\s]+$/.test(name)){
    toast('姓名只能含中文、字母和·，请勿填数字或特殊符号');return;
  }
  if(name.length>20){toast('姓名过长，请填写真实姓名');return}
  const dept=document.getElementById('fSDept').value;
  if(!dept){toast('请选择部门');return}
  const editing=!!user.name;
  // 修改时若当前身份下仍有在用/预约设备，禁止更改以保证记录可追溯、防止冒用
  if(editing&&hasActiveRecords()){
    toast('您有正在使用/预约的设备，请先归还或取消预约后再修改个人信息');
    return;
  }
  user.name=name;user.dept=dept;user.locked=true;
  saveUser();closeM('mSetup');renderNav();renderDevices();
  toast((editing?'个人信息已更新：':'个人信息已设置：')+name+' · '+dept);
}
function renderNav(){
  const el=document.getElementById('navUser');
  if(user.name){el.innerHTML=`${user.name} · ${user.dept} <span style="opacity:.4;font-size:11px">▾</span>`}
  else{el.innerHTML='设置姓名 <span style="opacity:.4;font-size:11px">▾</span>'}
}

/* ===== MODAL HELPERS ===== */
function openM(id){document.getElementById(id).classList.add('open');document.body.style.overflow='hidden'}
function closeM(id){document.getElementById(id).classList.remove('open');document.body.style.overflow=''}

/* ===== CHECKOUT ===== */
function openCheckout(){
  if(!user.name){openSetup(false);return}
  const sel=document.getElementById('fCODev');sel.innerHTML='';
  const avail=DEVS.filter(d=>!checkouts[d.id]&&!pendings[d.id]&&d.status!=='broken');
  if(!avail.length){sel.innerHTML='<option disabled>暂无可用设备</option>'}
  else{avail.forEach(d=>{sel.innerHTML+=`<option value="${d.id}">${d.name}（${d.series}）</option>`})}
  document.getElementById('fCOPurpose').value='';
  document.getElementById('fCODur').value='4';
  openM('mCO');
}
function openCOFor(id){
  if(!user.name){openSetup(false);return}
  const sel=document.getElementById('fCODev');
  const d=DEVS.find(x=>x.id===id);
  sel.innerHTML=`<option value="${d.id}">${d.name}（${d.series}）</option>`;
  document.getElementById('fCOPurpose').value='';
  document.getElementById('fCODur').value='4';
  openM('mCO');
}
async function confirmCO(){
  const devId=document.getElementById('fCODev').value;
  const purpose=document.getElementById('fCOPurpose').value.trim();
  const hours=parseInt(document.getElementById('fCODur').value);
  if(!devId){toast('请选择设备');return}
  try{
    const s=await api('/api/checkout',{deviceId:devId,user:user.name,dept:user.dept,purpose,hours});
    closeM('mCO');await refresh();
    toast(s.msg||'已领用');
  }catch(e){toast(e.message)}
}

/* ===== RESERVE ===== */
function openRV(id){
  if(!user.name){openSetup(false);return}
  const d=DEVS.find(x=>x.id===id);rvId=id;
  const rv=reserves[id]||[];
  const pos=rv.length+1;                                  // 你排队后的位置
  const stTxt=pendings[id]?'当前待领取':(checkouts[id]?'当前使用中':'当前不可用');
  document.getElementById('rvDesc').textContent=`${d.name}（${d.series}）${stTxt}，预约后将在设备可用时为您保留。`;
  // 以"你的位置"为主信息，前面排队人数作为补充说明
  document.getElementById('rvQInfo').innerHTML=rv.length
    ? `您当前排在第 <b>${pos}</b> 位，前面还有 <b>${rv.length}</b> 人排队`
    : `当前无人排队，您将是第 <b>1</b> 位（即第一位预约）`;
  document.getElementById('fRVPurpose').value='';
  openM('mRV');
  setTimeout(()=>document.getElementById('fRVPurpose').focus(),100);
}
async function confirmRV(){
  if(!rvId)return;
  const purpose=document.getElementById('fRVPurpose').value.trim();
  try{
    const s=await api('/api/reserve',{deviceId:rvId,user:user.name,dept:user.dept,purpose});
    rvId=null;closeM('mRV');await refresh();
    toast(s.msg||'预约成功');
  }catch(e){toast(e.message)}
}
async function cancelRV(id){
  try{
    const s=await api('/api/cancel_reserve',{deviceId:id,user:user.name,dept:user.dept});
    await refresh();toast(s.msg||'已取消预约');
  }catch(e){toast(e.message)}
}

/* ===== RETURN ===== */
function openRT(id){
  retId=id;
  const c=checkouts[id],d=DEVS.find(x=>x.id===id);
  const elapsed=fDur(Date.now()-new Date(c.checkoutTime).getTime());
  document.getElementById('rtDesc').textContent=`${d.name} — 使用人：${c.user}（${c.dept}）— 已使用 ${elapsed}`;
  document.getElementById('fRTNote').value='';
  openM('mRT');
}
async function confirmRT(){
  if(!retId)return;
  const note=document.getElementById('fRTNote').value.trim();
  const d=DEVS.find(x=>x.id===retId);
  try{
    const s=await api('/api/return',{deviceId:retId,user:user.name,dept:user.dept,note});
    retId=null;closeM('mRT');await refresh();
    toast(s.msg||`${d.name} 已归还`);
    if(s.notify)setTimeout(()=>toast(s.notify),800);
  }catch(e){toast(e.message)}
}

/* ===== CLAIM ===== */
function openCL(id){
  clId=id;
  const p=pendings[id],d=DEVS.find(x=>x.id===id);
  document.getElementById('clDesc').textContent=`${d.name}（${d.series}）已为您保留，确认后即可领用。用途：${p.purpose||'未填写'}`;
  document.getElementById('fCLDur').value='4';
  openM('mCL');
}
async function confirmCL(){
  if(!clId)return;
  const hours=parseInt(document.getElementById('fCLDur').value);
  try{
    const s=await api('/api/claim',{deviceId:clId,user:user.name,dept:user.dept,hours});
    clId=null;closeM('mCL');await refresh();
    toast(s.msg||'已领取');
  }catch(e){toast(e.message)}
}
function declineCL(){
  if(!clId)return;declineCLDirect(clId);closeM('mCL');
}
async function declineCLDirect(id){
  try{
    const s=await api('/api/decline_claim',{deviceId:id});
    await refresh();toast(s.msg||'已释放');
  }catch(e){toast(e.message)}
}

/* ===== ADD DEVICE ===== */
function openAddDevice(){
  document.getElementById('fADName').value='';
  document.getElementById('fADSeries').value='';
  document.getElementById('fADSN').value='';
  openM('mAD');
  setTimeout(()=>document.getElementById('fADName').focus(),100);
}
async function confirmAddDevice(){
  const name=document.getElementById('fADName').value.trim();
  const series=document.getElementById('fADSeries').value.trim();
  const sn=document.getElementById('fADSN').value.trim();
  if(!name){toast('请输入设备名称');return}
  if(!series){toast('请输入产品线');return}
  if(!sn){toast('请输入序列号');return}
  try{
    const s=await api('/api/add_device',{name,series,sn});
    closeM('mAD');await refresh();
    toast(s.msg||'设备已添加');
  }catch(e){toast(e.message)}
}

/* ===== BROKEN / REPAIR ===== */
function openBroken(id){
  bkId=id;
  const d=DEVS.find(x=>x.id===id);
  document.getElementById('bkDesc').textContent=`将 ${d.name}（${d.series}）标记为故障/维修中，标记后其他人将无法领用。`;
  document.getElementById('fBKNote').value='';
  openM('mBK');
  setTimeout(()=>document.getElementById('fBKNote').focus(),100);
}
async function confirmBroken(){
  if(!bkId)return;
  const note=document.getElementById('fBKNote').value.trim();
  try{
    const s=await api('/api/report_broken',{deviceId:bkId,user:user.name,note});
    bkId=null;closeM('mBK');await refresh();
    toast(s.msg||'已报修');
  }catch(e){toast(e.message)}
}
async function repairDev(id){
  try{
    const s=await api('/api/repair',{deviceId:id});
    await refresh();toast(s.msg||'已恢复为可用');
  }catch(e){toast(e.message)}
}

/* ===== EDIT DEVICE ===== */
function openEditDevice(id){
  edId=id;
  const d=DEVS.find(x=>x.id===id);
  document.getElementById('fEDName').value=d.name;
  document.getElementById('fEDSeries').value=d.series;
  document.getElementById('fEDSN').value=d.sn;
  openM('mED');
  setTimeout(()=>document.getElementById('fEDName').focus(),100);
}
async function confirmEditDevice(){
  if(!edId)return;
  const name=document.getElementById('fEDName').value.trim();
  const series=document.getElementById('fEDSeries').value.trim();
  const sn=document.getElementById('fEDSN').value.trim();
  if(!name){toast('请输入设备名称');return}
  if(!series){toast('请输入产品线');return}
  if(!sn){toast('请输入序列号');return}
  try{
    const s=await api('/api/edit_device',{deviceId:edId,name,series,sn,dept:user.dept});
    edId=null;closeM('mED');await refresh();
    toast(s.msg||'设备信息已更新');
  }catch(e){toast(e.message)}
}

/* ===== DELETE DEVICE ===== */
function openDelDevice(id){
  delId=id;
  const d=DEVS.find(x=>x.id===id);
  document.getElementById('delDesc').textContent=`确认删除 ${d.name}（${d.series} · ${d.sn}）？此操作不可撤销。`;
  openM('mDEL');
}
async function confirmDelDevice(){
  if(!delId)return;
  try{
    const s=await api('/api/delete_device',{deviceId:delId,dept:user.dept});
    delId=null;closeM('mDEL');await refresh();
    toast(s.msg||'设备已删除');
  }catch(e){toast(e.message)}
}

/* ===== EXPORT ===== */
function exportCSV(){
  if(!hist.length){toast('暂无记录可导出');return}
  const p=n=>String(n).padStart(2,'0');
  let csv='﻿设备名称,产品线,使用人,部门,用途,领用时间,归还时间,时长,备注\n';
  hist.forEach(h=>{
    csv+=`${h.deviceName},${h.series},${h.user},${h.dept},${h.purpose||''},${fTF(h.checkoutTime)},${fTF(h.returnTime)},${fDur(new Date(h.returnTime)-new Date(h.checkoutTime))},${h.note||''}\n`;
  });
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`设备记录_${new Date().toISOString().slice(0,10)}.csv`;a.click();URL.revokeObjectURL(a.href);
  toast('记录已导出');
}

/* ===== TOAST ===== */
function toast(msg){
  const r=document.getElementById('tr'),el=document.createElement('div');
  el.className='toast';el.textContent=msg;r.appendChild(el);
  setTimeout(()=>{el.classList.add('out');setTimeout(()=>el.remove(),300)},2600);
}

/* ===== KEYBOARD ===== */
document.addEventListener('keydown',e=>{
  if(document.querySelector('.modal-bg.open'))return;
  if(e.key==='ArrowRight')next();
  if(e.key==='ArrowLeft')prev();
});

/* ===== WHEEL — 鼠标滚轮前后翻页 ===== */
let wheelLock=false;
window.addEventListener('wheel',e=>{
  if(document.querySelector('.modal-bg.open'))return;          // 弹窗打开时不翻页
  if(Math.abs(e.deltaY)<8)return;                              // 忽略微小抖动
  if(wheelLock)return;                                         // 翻页冷却中
  // 若滚轮发生在可滚动内容区（设备表/记录表），且该区域还能继续滚动，则让内容滚动，不翻页
  const sc=(e.target instanceof Element)?e.target.closest('.t-wrap,.h-wrap'):null;
  if(sc){
    const atTop=sc.scrollTop<=0;
    const atBottom=sc.scrollTop+sc.clientHeight>=sc.scrollHeight-1;
    if((e.deltaY<0&&!atTop)||(e.deltaY>0&&!atBottom))return;
  }
  if(e.deltaY>0)next();else prev();
  wheelLock=true;
  setTimeout(()=>{wheelLock=false},800);                       // 与翻页动画时长匹配，避免连翻
},{passive:true});

/* ===== INIT ===== */
loadUser();
renderNav();
if(!user.name)openSetup(false);
updateSlideUI();
refresh();
setInterval(()=>{
  if(document.querySelector('.modal-bg.open'))return;   // 弹窗打开时不刷新，避免打断操作
  if(curPage===1||curPage===2)refresh();
},30000);
