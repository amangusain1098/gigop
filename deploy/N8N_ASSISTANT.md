# n8n Assistant Webhook

GigOptimizer Pro now supports an `n8n` assistant mode through the existing AI settings.

Use these settings:

- `AI_PROVIDER=n8n`
- `AI_API_BASE_URL=https://your-n8n-domain/webhook/gigoptimizer-assistant`

GigOptimizer sends:

```json
{
  "message": "What title should I use?",
  "context": {
    "optimization_score": 94,
    "recommended_title": "I will optimize WordPress speed and improve PageSpeed Insights",
    "recommended_tags": ["wordpress speed", "pagespeed insights"],
    "market_anchor_price": 40,
    "competitor_count": 12,
    "why_competitors_win": ["Competitors show more visible review volume."],
    "what_to_implement": ["Add PageSpeed Insights to the visible title."],
    "pricing_strategy": ["Use the Standard package as the value anchor."],
    "trust_boosters": ["Add one before-and-after result near the top."],
    "faq_recommendations": ["Can you improve both mobile and desktop scores?"],
    "persona_focus": [{"persona": "WooCommerce Store Owner", "score": 0.5}],
    "scraper_status": "ok",
    "scraper_message": "Compared your gig against 12 public Fiverr gigs in the same niche.",
    "hostinger": {
      "status": "ok"
    }
  }
}
```

Your n8n webhook should respond with:

```json
{
  "reply": "Use the search-match title because it aligns with the strongest Fiverr phrasing right now.",
  "suggestions": [
    "Queue the recommended title into HITL.",
    "Move PageSpeed Insights into the first paragraph.",
    "Add a concrete before-and-after proof line."
  ]
}
```

Suggested n8n flow:

1. `Webhook` node receives the GigOptimizer payload.
2. `Code` node compresses the context into a short working summary.
3. `OpenAI` or other LLM node generates the answer.
4. `Respond to Webhook` returns `reply` and `suggestions`.

Use this mode when you want the assistant orchestration outside the app while keeping the same floating copilot UI inside GigOptimizer.
