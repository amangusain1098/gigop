const DEFAULT_API_BASE = 'https://animha.co.in'

async function getSettings() {
  const values = await chrome.storage.sync.get({
    apiBaseUrl: DEFAULT_API_BASE,
    apiToken: '',
    gigUrl: '',
    keywordOverride: '',
  })
  return values
}

async function sendImport(payload) {
  const settings = await getSettings()
  if (!settings.apiToken) {
    throw new Error('Set your extension API token before sending data.')
  }

  const response = await fetch(`${settings.apiBaseUrl.replace(/\/$/, '')}/api/extension/import`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${settings.apiToken}`,
    },
    body: JSON.stringify({
      ...payload,
      gig_url: String(settings.gigUrl || payload.gig_url || '').trim(),
      keyword: String(settings.keywordOverride || payload.keyword || '').trim(),
    }),
  })

  const result = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(result.error || result.detail || `Import failed with status ${response.status}.`)
  }
  return result
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'SEND_FIVERR_IMPORT') {
    return false
  }

  sendImport(message.payload)
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: error?.message || 'Unable to send Fiverr import.' }))
  return true
})
