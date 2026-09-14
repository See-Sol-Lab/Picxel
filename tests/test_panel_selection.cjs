const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../scripts/panel.html'), 'utf8');
const context = vm.createContext({});
vm.runInContext(html.slice(html.indexOf('function mergePickedImages('), html.indexOf('\nasync function save(')), context);
const merge = (current, paths) => JSON.parse(JSON.stringify(context.mergePickedImages(current, paths)));

test('batch selection adds one image at a time in selection order', () => {
  let current = {mode:'batch', import:'', files:[]};
  for (const name of ['apple.png', 'cake.jpg', 'wine.webp']) {
    current = {...current, ...merge(current, ['C:/assets/' + name])};
  }
  assert.deepEqual(current.files, ['apple.png', 'cake.jpg', 'wine.webp']);
});

test('overlapping selections deduplicate Windows paths and keep original names', () => {
  const current = {mode:'batch', import:'C:\\Assets', files:['Apple.PNG']};
  assert.deepEqual(merge(current, ['c:/assets/apple.png', 'c:/assets/cake.jpg', 'c:/assets/cake.jpg']),
    {import:'C:\\Assets', files:['Apple.PNG', 'cake.jpg']});
  assert.deepEqual(current.files, ['Apple.PNG']);
});

test('single mode replaces the previous selection and cancel preserves it', () => {
  const current = {mode:'single', import:'C:/assets', files:['apple.png']};
  assert.deepEqual(merge(current, ['D:/new/cake.png']), {import:'D:/new', files:['cake.png']});
  assert.deepEqual(merge(current, []), {import:current.import, files:current.files});
});

test('other folders and mixed folders do not discard selected images', () => {
  const current = {mode:'batch', import:'C:/assets', files:['apple.png']};
  assert.throws(() => merge(current, ['D:/other/cake.png']), /同一文件夹/);
  assert.throws(() => merge({...current, files:[]}, ['C:/assets/a.png', 'D:/other/b.png']), /同一个文件夹/);
  assert.deepEqual(current.files, ['apple.png']);
});

test('the 20-image limit is applied after deduplication', () => {
  const current = {mode:'batch', import:'C:/assets', files:Array.from({length:20}, (_, i) => i+'.png')};
  assert.equal(merge(current, ['C:/assets/0.png']).files.length, 20);
  assert.throws(() => merge(current, ['C:/assets/extra.png']), /最多 20/);
  assert.equal(current.files.length, 20);
});

test('case-sensitive paths remain distinct on Unix', () => {
  const current = {mode:'batch', import:'/assets', files:['A.png']};
  assert.deepEqual(merge(current, ['/assets/a.png']).files, ['A.png', 'a.png']);
  assert.throws(() => merge(current, ['/Assets/b.png']), /同一文件夹/);
});
