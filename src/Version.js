var BUILD_INFO = {
  version: "v0.2.1 (Rev. Jun 16, 2026 07:54)",
  buildDate: "2026-06-16T14:54:27.020Z",
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
