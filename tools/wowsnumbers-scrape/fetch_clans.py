import requests, re, json, time, os, sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

COOKIE=("searchMode=%7B%22value%22%3A%22clan%22%7D; PHPSESSID=5kkn9al3dk860g76rhg9jer0m7; "
"_ga=GA1.1.1008971261.1787552853; apiConsent=1; "
"_hjSessionUser_143108=eyJpZCI6ImE2ZmJhZWVkLWYxNjUtNWYzZC1hNTVkLWFmMDJkY2QzYWVkNyIsImNyZWF0ZWQiOjE3ODc1NTI4NTkxODksImV4aXN0aW5nIjp0cnVlfQ==; "
"theme=light; "
"_hjSession_143108=eyJpZCI6IjI4OTA5YjJiLTFiODItNGI5MS1hMjMyLTk0N2Y1YWY1ZDJiYyIsImMiOjE3ODc2NDQxNzIxMDUsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowLCJzcCI6MX0=; "
"searchMode=%7B%22value%22%3A%22clan%22%7D; "
"cf_clearance=DsZsxYHxsiuUMrvoLOzUG4Zay5AM1QDQJD2lCccL63w-1787648178-1.2.1.1-GJ4st8LdIyXxmR.Sm_NX49hb8hAHRrjIm2C2WOMdhO6HSvJKz7pEgidlxjiBZ.kfD0YfjUBPtOdI.n28quiamr9M5RaXrWukZRjNPgfhHj8I3hcxxi6LJS_8.ouVafFFEaNaavkRII0sLXLdfZ9LVq26zjYobMNWX7TpelEvJDi8f_it2xbyzrkHH..izluqI.5Q7d0DEUpBUealbNUQc6Lsk_Zu..rFNZ2oTeg00fCx1iRhTBSYvDAO3UQ14sRzzP2TmlFjCj1KR3TIPUZPeIs9ETLYbQF1Cwy_DQUghciC6O9VJ._iCkZ7IZM_9QoI00EQsFD6.nPPIk3_IknQdpz2qWTfGDtoeNNbq1pz2ImNEMc.WO19KO3h9kDn3yLnaFP8Y0eliBOkFvc4MzdX7TV2rNvY4oSfUEZmnvCAPi4kBz0vGnM3tbZbbxg_PpVLcuWB7PPOGv3USeeWcFNIvw; "
"_ga_HCV2XML07J=GS2.1.s1787647394$o6$g1$t1787648290$j28$l0$h0")
HEADERS={'accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
 'accept-language':'zh-CN,zh;q=0.9,en;q=0.8,ru;q=0.7',
 'referer':'https://wows-numbers.com/clans/',
 'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'}

def parse(html):
    out=[]
    for m in re.finditer(r'href="/clan/(\d+),', html):
        out.append(int(m.group(1)))
    return out

def fetch(host, outpath):
    s=requests.Session()
    s.headers.update(HEADERS); s.headers['Cookie']=COOKIE
    retry=Retry(total=5, connect=5, read=5, status=5, backoff_factor=1.5,
                status_forcelist=[429,500,502,503,504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    order=json.load(open(outpath)) if os.path.exists(outpath) else []
    seen=set(order)
    for p in range(1, 400):
        url=f'https://{host}/clans/?p={p}'
        for attempt in range(5):
            try:
                r=s.get(url, timeout=45)
                if r.status_code!=200 or 'Just a moment' in r.text or '安全验证' in r.text:
                    print(f'{host} p{p} status={r.status_code} challenge', flush=True)
                    time.sleep(2+2*attempt); continue
                rows=parse(r.text)
                if not rows:
                    print(f'{host} done at p{p} (no rows)', flush=True); return order
                added=0
                for cid in rows:
                    if cid not in seen: seen.add(cid); order.append(cid); added+=1
                json.dump(order, open(outpath,'w'))
                print(f'{host} p{p}: +{added} total={len(order)}', flush=True)
                break
            except Exception as e:
                w=2+2*attempt
                print(f'{host} p{p} try{attempt} {repr(e)[:70]} wait {w}s', flush=True)
                time.sleep(w)
        else:
            print(f'{host} p{p} FAILED', flush=True); return order
        time.sleep(1.0)
    return order

if __name__=='__main__':
    host=sys.argv[1] if len(sys.argv)>1 else 'wows-numbers.com'
    tag=sys.argv[2] if len(sys.argv)>2 else 'eu'
    os.makedirs(r'D:\codexProject\wows-toolkit\input\clans', exist_ok=True)
    out=os.path.join(r'D:\codexProject\wows-toolkit\input\clans', f'{tag}_clans.json')
    res=fetch(host, out)
    print(f'FINAL {tag}: {len(res)} clans -> {out}')
