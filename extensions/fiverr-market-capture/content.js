const CARD_SELECTORS = [
  'article',
  '[data-testid="gig-card-layout"]',
  '[data-testid="gig-card"]',
  '.gig-card-layout',
]

const TITLE_SELECTORS = [
  '[data-testid="gig-card-title"]',
  'h3',
  'h2',
]

const LINK_SELECTORS = [
  'a[href*="/services/"]',
  'a[href*="/gig/"]',
  'a[href*="/categories/"]',
]

const PRICE_SELECTORS = [
  '[data-testid="gig-card-price"]',
  '[class*="price"]',
]

const RATING_SELECTORS = [
  '[data-testid="gig-card-rating"]',
  '[class*="rating"]',
]

const REVIEWS_SELECTORS = [
  '[data-testid="gig-card-reviews"]',
  '[class*="reviews"]',
]

const SELLER_SELECTORS = [
  '[data-testid="seller-name"]',
  '[class*="seller"]',
]

const DELIVERY_SELECTORS = [
  '[data-testid="delivery-time"]',
  '[class*="delivery"]',
]

function pickText(root, selectors) {
  for (const selector of selectors) {
    const node = root.querySelector(selector)
    const text = node?.textContent?.trim()
    if (text) return text
  }
  return ''
}

function pickLink(root) {
  for (const selector of LINK_SELECTORS) {
    const node = root.querySelector(selector)
    const href = node?.getAttribute('href') || ''
    if (href) return new URL(href, window.location.origin).toString()
  }
  return ''
}

function normalizeNumber(value) {
  const match = String(value || '').replace(/,/g, '').match(/(\d+(?:\.\d+)?)/)
  if (!match) return null
  return Number(match[1])
}

function extractGigs() {
  const cards = []
  for (const selector of CARD_SELECTORS) {
    cards.push(...document.querySelectorAll(selector))
    if (cards.length) break
  }

  const gigs = cards
    .map((card, index) => {
      const title = pickText(card, TITLE_SELECTORS)
      const url = pickLink(card)
      if (!title && !url) return null
      return {
        title,
        url,
        seller_name: pickText(card, SELLER_SELECTORS),
        starting_price: normalizeNumber(pickText(card, PRICE_SELECTORS)),
        rating: normalizeNumber(pickText(card, RATING_SELECTORS)),
        reviews_count: normalizeNumber(pickText(card, REVIEWS_SELECTORS)),
        delivery_days: normalizeNumber(pickText(card, DELIVERY_SELECTORS)),
        snippet: card.textContent?.trim()?.slice(0, 320) || '',
        rank_position: index + 1,
        page_number: 1,
        is_first_page: index < 10,
        badges: [],
      }
    })
    .filter(Boolean)

  return gigs.slice(0, 25)
}

function buildPayload(override = {}) {
  const url = new URL(window.location.href)
  const keyword = override.keyword || url.searchParams.get('query') || ''
  return {
    source: 'browser_extension',
    page_url: window.location.href,
    page_title: document.title,
    keyword: String(keyword || '').trim(),
    gig_url: String(override.gig_url || '').trim(),
    gigs: extractGigs(),
    captured_at: new Date().toISOString(),
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'CAPTURE_FIVERR_PAGE') {
    return false
  }
  try {
    const payload = buildPayload(message.payload || {})
    sendResponse({ ok: true, payload })
  } catch (error) {
    sendResponse({ ok: false, error: error?.message || 'Unable to capture the current Fiverr page.' })
  }
  return true
})
