// node --test guards.test.js — аудит 13.11.2026. Сломать: разрешить «@» в пути или частные адреса в /probe.
const test = require('node:test');
const assert = require('node:assert');
const { safePath, privateIp } = require('./guards');

test('путь страницы — только свой, относительный', () => {
  assert.ok(safePath('/deals/mp/pdf/render'));
  assert.ok(safePath('/directory/annexes/pdf/123'));
  for (const bad of ['@169.254.169.254/latest/meta-data/', '//evil.example/x', '/a/../b', 'http://x', '/a@b', '/a\\b', '']) {
    assert.equal(safePath(bad), false, bad);
  }
});

test('внутренние адреса запрещены', () => {
  for (const ip of ['127.0.0.1', '10.0.0.5', '172.18.0.3', '192.168.1.1', '169.254.169.254', '::1', 'fd00::1', '::ffff:10.0.0.1', '0.0.0.0']) {
    assert.ok(privateIp(ip), ip);
  }
  for (const ip of ['8.8.8.8', '93.184.216.34', '2a00:1450:4010:c05::64']) {
    assert.equal(privateIp(ip), false, ip);
  }
});

test('проверка баннера: счётчики и посадочная режутся, отрисовка идёт', () => {
  const { bannerRequestVerdict: v } = require('./guards');
  const o = { landing_host: 'landing.invalid', block_hosts: ['counter.example'], block_domain: 'dsp.example',
    allow_urls: ['https://static.dsp.example/engine/viewability.js'] };
  assert.equal(v('https://cdn.dsp-cdn.example/b/index.js', 'script', o), 'continue');
  assert.equal(v('https://cdn.dsp-cdn.example/b/bg.png', 'image', o), 'continue');
  assert.equal(v('https://static.dsp.example/engine/viewability.js', 'script', o), 'continue');
  assert.equal(v('https://static.dsp.example/engine/viewability.js?x=1', 'script', o), 'continue');
  assert.equal(v('https://log.dsp.example/new/vs?cr={CR_ID}', 'image', o), 'abort');      // маяк картинкой
  assert.equal(v('https://static.dsp.example/stableid/postView.js', 'script', o), 'abort');
  assert.equal(v('https://counter.example/afcar/qq.js', 'script', o), 'abort');
  assert.equal(v('https://landing.invalid/x', 'document', o), 'abort');
  assert.equal(v('https://any.example/api', 'xhr', o), 'abort');
  assert.equal(v('https://any.example/b', 'ping', o), 'abort');
  assert.equal(v('blob:https://x/1', 'document', o), 'abort');
  assert.equal(v('data:image/png;base64,AA', 'image', o), 'continue');
  assert.equal(v('file:///etc/passwd', 'image', o), 'abort');
});
