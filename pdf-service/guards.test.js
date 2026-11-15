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
