import {mkdirSync} from 'node:fs';
mkdirSync('test-results',{recursive:true});
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const origin=process.env.CLASSY_TEST_ORIGIN || 'http://127.0.0.1:4174';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
try{
  await page.goto(origin);
  await page.getByRole('heading',{name:'나에게 필요한 배움, CLASSY'}).waitFor();
  await page.evaluate(()=>document.fonts.ready);
  assert.match(await page.locator('body').evaluate(e=>getComputedStyle(e).fontFamily),/Pretendard/);
  const health=await page.request.get(origin+'/api/healthz/');
  assert.equal(health.status(),200);
  assert.equal((await health.json()).status,'ok');
  const subjects=await page.request.get(origin+'/api/accounts/subjects/');
  assert.equal(subjects.status(),200);
  assert.ok((await subjects.json()).length>0);
  const lectures=await page.request.get(origin+'/api/lectures/');
  assert.equal(lectures.status(),200);
  const catalog=await lectures.json();
  assert.ok(Array.isArray(catalog.results));
  assert.ok(catalog.results.every(x=>!Object.hasOwn(x,'video')));
  await page.goto(origin+'/#lectures');
  await page.getByRole('heading',{name:'강의 찾기',exact:true}).waitFor();
  if(catalog.count)await page.getByRole('heading',{name:catalog.results[0].title,exact:true}).waitFor();
  await page.getByRole('button',{name:'로그인',exact:true}).first().click();
  await page.getByRole('dialog').getByRole('button',{name:'회원가입',exact:true}).click();
  await page.getByRole('button',{name:'선생님으로 가입',exact:true}).waitFor();
  await page.keyboard.press('Escape');
  const locked=await page.request.get(origin+'/api/accounts/me/');
  assert.equal(locked.status(),401);
  for(const path of ['privacy','service-terms']){
    const expected=await readFile(new URL('../public/'+path+'.html',import.meta.url),'utf8');
    for(const suffix of ['', '/', '/?embed=1']){
      const response=await page.request.get(origin+'/'+path+suffix);
      assert.equal(response.status(),200);
      assert.equal(await response.text(),expected,'policy must be byte-identical: '+path+suffix);
    }
  }
  await page.screenshot({path:'test-results/aws-redesign-home.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS AWS Nginx application, local font, CSP, API proxy, anonymous authorization, and all 6 policy URLs');
}finally{await browser.close();}
