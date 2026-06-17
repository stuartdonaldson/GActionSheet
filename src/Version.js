var BUILD_INFO = {
  version: "v0.2.1 (Rev. Jun 16, 2026 20:41) (TEST)",
  buildDate: "2026-06-17T03:41:26.968Z",
  webappUrl: "https://script.google.com/macros/s/AKfycbzVloY3corgO5F9AV7XvAbkL1oaTaehcE1kXwmFdJsXZPBBCm3xJ4ONJsZADHH9Hm4/exec"
};

function getWebAppUrl() {
  return BUILD_INFO.webappUrl;
}

function _logVersionMismatch(parsed, logTag) {
  if (parsed && parsed.serverVersion && parsed.serverVersion !== BUILD_INFO.version) {
    GasLogger.log(logTag + '.version.mismatch', { client: BUILD_INFO.version, server: parsed.serverVersion });
  }
}
