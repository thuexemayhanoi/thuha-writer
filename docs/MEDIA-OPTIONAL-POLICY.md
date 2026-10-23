# Optional WordPress images — current production policy (23 October 2026)

**Owner instruction:** For `thuexemayhanoi/thuha-writer` and `rentbikehanoi.com`, external Claude/ChatGPT writers do NOT need to visit WordPress, inspect media, search images, choose a featured image, or check image alt text before writing, QA, submitting, or publishing.

- Write `"featured_media": null` in the article JSON if no real media ID is available. The Python publisher adapter sends `featured_media: 0` to WordPress; the plugin accepts zero (no thumbnail), and readback treats null and zero equivalently.
- `FEATURED_MEDIA` is retired as a QA hard failure and wait condition. No missing photo or image alt can prevent QA or publication. `pack` may show optional suggestions but an empty list is not a blocker.
- The QA policy stays **>=75/100 with no hard failures** for content, research, language, internal links, SEO, canonical, taxonomy, safety, originality and duplicate protection. The former 10/80 image criterion is neutral, preserving score comparability without forcing image selection.
- The legacy `recheck-data` path clears prior `FEATURED_MEDIA` waits **without contacting the photo library**. A draft whose remaining waits are all cleared moves to `DRAFT_READY` for ordinary QA; do not fabricate an automatic QA PASS.
- If an author voluntarily supplies a genuine WordPress media ID, the currently deployed plugin still checks that selected attachment is readable and has alt. To avoid WordPress media or alt inspection entirely, **leave featured_media null**. For embedded images, useful alt is recommended for accessibility.
- This current policy supersedes any V4/V5 historical docs/reports describing `NEEDS_MEDIA`, alt requirements or media-dependent waiting. It does **not** remove image HTML security checks, source verification, other waiting-data checks, or release authorization.
