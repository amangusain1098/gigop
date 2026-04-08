(function () {
  const syncButton = document.getElementById('manhwa-sync-button')
  const syncStatus = document.getElementById('manhwa-sync-status')
  const sourceForm = document.getElementById('manhwa-source-form')
  const sourceStatus = document.getElementById('manhwa-source-status')
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: 'Request failed.' }))
      throw new Error(payload.detail || 'Request failed.')
    }

    return response.json()
  }

  if (syncButton && syncStatus) {
    syncButton.addEventListener('click', async function () {
      syncButton.disabled = true
      syncStatus.textContent = 'Syncing feeds...'
      try {
        const payload = await postJson('/api/manhwa/sync', { force: true })
        const result = payload.result || {}
        syncStatus.textContent = `Sync complete. ${result.total_entries || 0} entries fetched, ${result.total_new_entries || 0} new.`
        window.setTimeout(() => window.location.reload(), 800)
      } catch (error) {
        syncStatus.textContent = error instanceof Error ? error.message : 'Sync failed.'
      } finally {
        syncButton.disabled = false
      }
    })
  }

  if (sourceForm && sourceStatus) {
    sourceForm.addEventListener('submit', async function (event) {
      event.preventDefault()
      const form = new FormData(sourceForm)
      const submitButton = sourceForm.querySelector('button[type="submit"]')
      if (submitButton) {
        submitButton.disabled = true
      }
      sourceStatus.textContent = 'Saving source...'
      try {
        await postJson('/api/manhwa/sources', {
          title: form.get('title'),
          feed_url: form.get('feed_url'),
          site_url: form.get('site_url'),
          category: form.get('category'),
          kind: form.get('kind'),
          focus: form.get('focus'),
          active: true,
        })
        sourceStatus.textContent = 'Source saved. Refreshing dashboard...'
        window.setTimeout(() => window.location.reload(), 800)
      } catch (error) {
        sourceStatus.textContent = error instanceof Error ? error.message : 'Unable to save source.'
      } finally {
        if (submitButton) {
          submitButton.disabled = false
        }
      }
    })
  }

  document.querySelectorAll('.source-toggle').forEach((button) => {
    button.addEventListener('click', async function () {
      const slug = button.getAttribute('data-source-slug') || ''
      const nextActive = (button.getAttribute('data-next-active') || 'true') === 'true'
      if (!slug) {
        return
      }
      button.disabled = true
      if (sourceStatus) {
        sourceStatus.textContent = `${nextActive ? 'Enabling' : 'Disabling'} source...`
      }
      try {
        await postJson(`/api/manhwa/sources/${slug}/toggle`, { active: nextActive })
        if (sourceStatus) {
          sourceStatus.textContent = 'Source updated. Refreshing dashboard...'
        }
        window.setTimeout(() => window.location.reload(), 800)
      } catch (error) {
        if (sourceStatus) {
          sourceStatus.textContent = error instanceof Error ? error.message : 'Unable to update source.'
        }
      } finally {
        button.disabled = false
      }
    })
  })
})()
