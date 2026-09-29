import {mkdirSync} from 'node:fs';
mkdirSync('test-results',{recursive:true});
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1440,height:1050}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try {
await page.goto('http://127.0.0.1:4173');
await page.getByRole('heading',{name:'나에게 필요한 배움, CLASSY'}).waitFor();
await page.evaluate(()=>document.fonts.ready);
await page.screenshot({path:'test-results/redesign-home-desktop.png',fullPage:true});
await page.getByRole('navigation',{name:'주요 메뉴',exact:true}).getByRole('link',{name:'강의',exact:true}).click();
await page.getByRole('button',{name:'로그인',exact:true}).first().click();
await page.getByLabel('이메일',{exact:true}).fill('web-test@example.invalid');
await page.getByLabel('비밀번호',{exact:true}).fill('mock-password');
await page.route('**/api/accounts/login/',r=>r.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Invalid credentials'})}));
await page.getByRole('dialog').getByRole('button',{name:'로그인',exact:true}).click();
await page.getByRole('alert').filter({hasText:'이메일 또는 비밀번호'}).waitFor();
await page.keyboard.press('Escape');
await page.goto('http://127.0.0.1:4173/#posts');
await page.getByRole('heading',{name:'과외 찾기',exact:true}).waitFor();
await page.screenshot({path:'test-results/redesign-posts-guest.png',fullPage:true});
for(const width of [390,768,1024]){
  await page.setViewportSize({width,height:844});
  await page.goto('http://127.0.0.1:4173/#home');
  await page.getByRole('heading',{name:'나에게 필요한 배움, CLASSY'}).waitFor();
  await page.evaluate(()=>document.fonts.ready);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'overflow at '+width);
  if(width===390){
    await page.screenshot({path:'test-results/redesign-home-mobile.png',fullPage:true});
    await page.getByRole('navigation',{name:'모바일 메뉴',exact:true}).getByRole('link',{name:'과외',exact:true}).click();
    await page.getByRole('textbox',{name:'검색',exact:true}).waitFor();
    await page.screenshot({path:'test-results/redesign-tutoring-mobile.png',fullPage:true});
  }
}
assert.deepEqual(errors,[]);
console.log('PASS guest navigation, login failure, keyboard modal, mobile bottom navigation, 390/768/1024 overflow checks');
} finally {await browser.close();}
