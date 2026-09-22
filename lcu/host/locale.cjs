'use strict';

// runtimeIntlConfig is trusted renderer input. Preserve it exactly: React Intl
// accepts compiled message ASTs as well as strings, and also consumes options
// beyond locale/messages (formats, defaultLocale, timeZone, onError, etc.).
// This adapter only supplies the same empty-catalog fallback used by the host
// when no runtime config is available; it does not validate or rewrite caller
// data and never invents translations.
function resolveRuntimeIntl(config, systemLocale = 'en-US') {
  if (config !== null && typeof config === 'object' && !Array.isArray(config)) {
    return config;
  }
  return { defaultLocale: 'en-US', locale: systemLocale, messages: {} };
}

module.exports = { resolveRuntimeIntl };
