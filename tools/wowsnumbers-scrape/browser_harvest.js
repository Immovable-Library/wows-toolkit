// wows-numbers 工会榜采集脚本：粘贴到浏览器控制台(F12 -> Console)运行。
// 会自动翻页把整份榜单按顺序攒下来，最后下载 clans.json。
(function(){
  const KEY='wn_clans';
  const read=()=>{try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return []}};
  const write=a=>localStorage.setItem(KEY,JSON.stringify(a));
  function harvest(){
    const acc=read(); const seen=new Set(acc.map(x=>x.id));
    document.querySelectorAll('a[href]').forEach(a=>{
      const h=a.getAttribute('href')||'';
      const m=h.match(/clan[^0-9]*([0-9]{6,10})/i);
      if(!m) return;
      const id=m[1];
      if(seen.has(id)) return;
      const row=a.closest('tr')||a.closest('li')||a.parentElement;
      acc.push({id:id, label:(a.textContent||'').trim(), context:((row&&row.textContent)||'').replace(/\s+/g,' ').trim().slice(0,80)});
      seen.add(id);
    });
    write(acc); return acc.length;
  }
  function findNext(){
    const sels=['a[rel="next"]','.pagination a:last-child','a.next','a[aria-label*="next"]','a[aria-label*="Next"]'];
    for(const s of sels){const e=document.querySelector(s); if(e) return e;}
    const as=[...document.querySelectorAll('a')];
    return as.find(a=>/^\s*(next|>|»|›|下一页)\s*$/i.test(a.textContent||'')) ||
           as.find(a=>/next|下一页|»|›/i.test(a.textContent||'')&&/pagination|page/i.test((a.getAttribute('class')||'')));
  }
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  window.exportClans=async()=>{
    const acc=read();
    const blob=new Blob([JSON.stringify({region:location.hostname, count:acc.length, clans:acc})],{type:'application/json'});
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);
    a.download='wn_clans_'+location.hostname.replace(/\W/g,'_')+'.json';a.click();
    console.log('downloaded',acc.length,'clans');
    return acc;
  };
  window.resetClans=()=>{localStorage.removeItem(KEY); console.log('reset')};
  (async()=>{
    let total=harvest();
    console.log('page 1 -> total',total);
    let p=1;
    while(p<500){
      const next=findNext();
      if(!next){console.log('no next button found');break;}
      const before=read().length;
      next.click();
      await sleep(2000);
      const after=harvest();
      console.log('page',++p,'-> total',after);
      if(after===before){console.log('no new rows, stopping');break;}
    }
    console.log('DONE. Total clans:',read().length,'. Auto-downloading...');
    await window.exportClans();
  })();
})();
