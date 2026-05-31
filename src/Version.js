var BUILD_INFO = {
  version: "v0.1.0 (Rev. May 30, 2026 22:35) (DEV)",
  buildDate: "2026-05-31T05:35:51.572Z",
  webappUrl: ""
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
