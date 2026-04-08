const apiBaseUrlInput = document.getElementById('apiBaseUrl')
const apiTokenInput = document.getElementById('apiToken')
const gigUrlInput = document.getElementById('gigUrl')
const keywordOverrideInput = document.getElementById('keywordOverride')
const saveSettingsButton = document.getElementById('saveSettings')
const captureButton = document.getElementById('captureNow')
const statusBox = document.getElementById('status')

function setStatus(message, isError = false) {
  statusBox.textContent = message
  statusBox.style.color = isError ? '#ffd1d1' : '#ebf4ff'
}

async function loadSettings() {
  const values = await chrome.storage.sync.get({
    apiBaseUrl: 'https://animha.co.in',
    apiToken: '',
    gigUrl: '',
    keywordOverride: '',
  })
  apiBaseUrlInput.value = values.apiBaseUrl
  apiTokenInput.value = values.apiToken
  gigUrlInput.value = values.gigUrl
  keywordOverrideInput.value = values.keywordOverride
}

async function saveSettings() {
  await chrome.storage.sync.set({
    apiBaseUrl: apiBaseUrlInput.value.trim(),
    apiToken: apiTokenInput.value.trim(),
    gigUrl: gigUrlInput.value.trim(),
    keywordOverride: keywordOverrideInput.value.trim(),
  })
  setStatus('Settings saved.')
}

async function captureNow() {
  setStatus('Capturing the current Fiverr page...')
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id || !tab.url?.includes('fiverr.com')) {
    setStatus('Open a Fiverr search or gig page first.', true)
    return
  }

  const settings = await chrome.storage.sync.get({
    gigUrl: '',
    keywordOverride: '',
  })

  chrome.tabs.sendMessage(
    tab.id,
    {
      type: 'CAPTURE_FIVERR_PAGE',
      payload: {
        gig_url: settings.gigUrl,
        keyword: settings.keywordOverride,
      },
    },
    (captureResponse) => {
      if (chrome.runtime.lastError) {
        setStatus(chrome.runtime.lastError.message || 'Unable to read the Fiverr page.', true)
        return
      }
      if (!captureResponse?.ok) {
        setStatus(captureResponse?.error || 'The extension could not capture the current page.', true)
        return
      }

      setStatus(`Captured ${captureResponse.payload?.gigs?.length || 0} visible gigs. Sending to GigOptimizer...`)
      chrome.runtime.sendMessage(
        {
          type: 'SEND_FIVERR_IMPORT',
          payload: captureResponse.payload,
        },
        (sendResponse) => {
          if (chrome.runtime.lastError) {
            setStatus(chrome.runtime.lastError.message || 'Unable to send the import.', true)
            return
          }
          if (!sendResponse?.ok) {
            setStatus(sendResponse?.error || 'GigOptimizer rejected the import.', true)
            return
          }
          const comparison = sendResponse.result?.gig_comparison || {}
          const title = comparison.implementation_blueprint?.recommended_title || 'No title yet'
          setStatus(
            `Imported ${comparison.competitor_count || 0} gigs for "${comparison.primary_search_term || captureResponse.payload.keyword || 'market'}".\nRecommended title: ${title}`,
          )
        },
      )
    },
  )
}

saveSettingsButton.addEventListener('click', () => {
  void saveSettings()
})

captureButton.addEventListener('click', () => {
  void captureNow()
})

void loadSettings()
