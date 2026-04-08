(function () {
  function announce() {
    window.postMessage(
      {
        source: 'gigoptimizer-extension',
        type: 'ready',
        version: chrome.runtime.getManifest().version,
      },
      window.location.origin,
    )
  }

  announce()

  window.addEventListener('message', (event) => {
    if (event.source !== window) return
    const payload = event.data
    if (!payload || payload.source !== 'gigoptimizer-dashboard') return
    if (payload.type === 'gigoptimizer-extension-ping') {
      announce()
    }
  })
})()
