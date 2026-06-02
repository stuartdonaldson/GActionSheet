var BUILD_INFO = {
  version: "v0.2.0 (Rev. Jun 2, 2026 06:03) (TEST)",
  buildDate: "2026-06-02T13:03:37.919Z",
  webappUrl: "https://script.google.com/macros/s/AKfycbzVloY3corgO5F9AV7XvAbkL1oaTaehcE1kXwmFdJsXZPBBCm3xJ4ONJsZADHH9Hm4/exec"
};

function getWebAppUrl() {
  if (BUILD_INFO.webappUrl) return BUILD_INFO.webappUrl;
  return PropertiesService.getScriptProperties().getProperty('WEBAPP_URL');
}

function _logVersionMismatch(parsed, logTag) {
  if (parsed && parsed.serverVersion && parsed.serverVersion !== BUILD_INFO.version) {
    GasLogger.log(logTag + '.version.mismatch', { client: BUILD_INFO.version, server: parsed.serverVersion });
  }
}
