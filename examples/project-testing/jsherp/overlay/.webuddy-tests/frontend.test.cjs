const {test,before} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let utils;
before(async()=>{
  const context = vm.createContext({console,Date,Math,Object,Array,Symbol,setTimeout,clearTimeout});
  const module = new vm.SourceTextModule(fs.readFileSync('jshERP-web/src/utils/util.js','utf8'),{context});
  await module.link(async spec=>{
    // These dependencies are not called by the pure business functions under test.
    const values = spec==='@/utils/validate' ? {isURL:()=>{throw Error('unexpected URL dependency')}} : spec==='@/api/manage' ? {downFilePost:()=>{throw Error('unexpected network call')}} : {default:{}};
    return new vm.SyntheticModule(Object.keys(values),function(){for(const [k,v]of Object.entries(values))this.setExport(k,v)},{context});
  });
  await module.evaluate();utils=module.namespace;
});
test('large identifiers sum beyond JavaScript safe integer',()=>assert.equal(utils.addBigNumbers('9007199254740993','9'),'9007199254741002'));
test('large identifiers propagate final carry',()=>assert.equal(utils.addBigNumbers('999999999999999999','1'),'1000000000000000000'));
test('large identifiers zero',()=>assert.equal(utils.addBigNumbers('0','0'),'0'));
test('approval blocks selected document type',()=>assert.equal(utils.getCheckFlag('CGDD,XSCK','1','XSCK'),false));
test('approval allows unrelated document type',()=>assert.equal(utils.getCheckFlag('CGDD,XSCK','1','QTCK'),true));
test('approval disabled permits normal flow',()=>assert.equal(utils.getCheckFlag('XSCK','0','XSCK'),true));
test('approval without configured types permits normal flow',()=>assert.equal(utils.getCheckFlag('','1','XSCK'),true));
test('refund list negates each amount',()=>assert.equal(JSON.stringify(utils.changeListFmtMinus('12.50,3.25')),JSON.stringify(['-12.5','-3.25'])));
test('refund keeps already negative amount',()=>assert.equal(JSON.stringify(utils.changeListFmtMinus('-12.50,3.25')),JSON.stringify(['-12.5','-3.25'])));
test('single refund amount stays one amount',()=>assert.equal(JSON.stringify(utils.changeListFmtMinus('12.50')),JSON.stringify(['-12.5'])));
test('blank refund list remains empty',()=>assert.equal(JSON.stringify(utils.changeListFmtMinus('')),JSON.stringify([])));
test('filters empty search terms while preserving zero and false',()=>{
 const result=utils.filterObj({price:0,active:false,term:'',missing:null,category:'食品'});
 assert.equal(JSON.stringify(result),JSON.stringify({price:0,active:false,category:'食品'}));
});
test('merges search state without dropping sibling fields',()=>{
 const result=utils.mergeRecursive({filter:{status:'open',tenant:'T1'}},{filter:{status:'closed'}});
 assert.equal(JSON.stringify(result),JSON.stringify({filter:{status:'closed',tenant:'T1'}}));
});
test('large identifier sums agree with exact integer arithmetic across carry boundaries',()=>{
 for(let n=1;n<=80;n++){
  const a='9'.repeat(n),b=String(n*137);
  assert.equal(utils.addBigNumbers(a,b),String(BigInt(a)+BigInt(b)));
 }
});
