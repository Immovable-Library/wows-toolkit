const puppeteer = require('puppeteer-core');
const fs = require('fs');
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox','--disable-blink-features=AutomationControlled','--lang=zh-CN','--window-size=1400,900']
  });
  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
  });
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36');
  await page.goto('https://wows-numbers.com/clans/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  for (let i = 0; i < 45; i++) {
    const t = await page.title().catch(() => '');
    if (t && !t.includes('Just a moment')) break;
    await sleep(1000);
  }
  await sleep(3000);
  const title = await page.title();
  const html = await page.content();
  console.log('TITLE:', title);
  console.log('LEN:', html.length);
  fs.writeFileSync('clans_eu.html', html, 'utf8');
  console.log('cf_clearance?', (await page.cookies()).some(c => c.name === 'cf_clearance'));
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
