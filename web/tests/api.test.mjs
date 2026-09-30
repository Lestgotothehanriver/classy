import test from 'node:test';
import assert from 'node:assert/strict';
import {apiPath,errorText,list} from '../src/api.js';
test('pagination URLs stay on the fixed Classy origin',()=>{
 assert.equal(apiPath('/lectures/?page=2'),'/api/lectures/?page=2');
 assert.equal(apiPath('https://api.classystudy.com/lectures/?page=2'),'/api/lectures/?page=2');
 assert.throws(()=>apiPath('https://evil.example/accounts/me/'));
 assert.throws(()=>apiPath('//evil.example/accounts/me/'));
});
test('supports array and paginated API responses',()=>{assert.deepEqual(list([{id:1}]),[{id:1}]);assert.deepEqual(list({results:[{id:2}]}),[{id:2}]);assert.deepEqual(list(null),[]);});
test('renders DRF validation and login errors readably',()=>{assert.match(errorText({error:'Invalid credentials'}),/비밀번호/);assert.equal(errorText({email:['이메일을 확인해 주세요.']}),'이메일을 확인해 주세요.');});
