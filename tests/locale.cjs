'use strict';
const assert = require('node:assert/strict');
const { resolveRuntimeIntl } = require('../lcu/host/locale.cjs');

const ast = [{ type: 0, value: 'Bonjour ' }, { type: 1, value: 'name' }];
const formats = { date: { short: { year: 'numeric' } } };
const onError = () => {};
const supplied = {
  locale: 'fr_CA', defaultLocale: 'en', messages: { greeting: ast },
  formats, defaultFormats: { date: { short: {} } }, timeZone: 'Europe/Paris',
  fallbackOnEmptyString: false, onError,
};

// Preserve the original object and its React Intl-specific runtime values.
assert.equal(resolveRuntimeIntl(supplied, 'de-DE'), supplied);
assert.equal(resolveRuntimeIntl(supplied).messages.greeting, ast);
assert.equal(resolveRuntimeIntl(supplied).formats, formats);
assert.equal(resolveRuntimeIntl(supplied).onError, onError);

assert.deepEqual(resolveRuntimeIntl(null, 'de-DE'), {
  defaultLocale: 'en-US', locale: 'de-DE', messages: {},
});
assert.deepEqual(resolveRuntimeIntl(undefined), {
  defaultLocale: 'en-US', locale: 'en-US', messages: {},
});
