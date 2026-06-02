var BUILD_INFO = {
  version: "v0.2.0 (Rev. Jun 2, 2026 02:10) (DEV)",
  buildDate: "2026-06-02T09:10:09.744Z",
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
