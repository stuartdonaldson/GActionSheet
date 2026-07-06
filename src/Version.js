var BUILD_INFO = {
  version: "v0.2.2 (Rev. Jul 6, 2026 14:04)",
  buildDate: "2026-07-06T21:04:12.816Z",
  webappUrl: "https://script.google.com/macros/s/AKfycbynLp8FjYKRVuPVrxtwmcaOfrhntzPm7FhfRsix1QP97mVGVU49ExDzhx7GytchgBkC/exec"
};

function getWebAppUrl() {
  return BUILD_INFO.webappUrl;
}

function _logVersionMismatch(parsed, logTag) {
  if (parsed && parsed.serverVersion && parsed.serverVersion !== BUILD_INFO.version) {
    GasLogger.log(logTag + '.version.mismatch', { client: BUILD_INFO.version, server: parsed.serverVersion });
  }
}
