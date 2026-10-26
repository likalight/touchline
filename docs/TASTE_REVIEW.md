# Matchday presentation review

Applied `design-taste-frontend` to the consumer demo entrance and presentation on
26 October 2026. The full studio is a dense product surface, outside that skill's primary
scope; its working controls and information architecture remain in place.

## Design read and audit

This is an overhaul of a football storytelling demo for judges and fans. The direction is
premium sports broadcast, with native CSS, self-hosted Barlow typography and graphite,
off-white and citron. It does not claim to implement Fluent UI. Dials: design variance 7,
motion 4, density 4. The existing app supplies the data views, not invented product mockups.

The prior presentation used deep turf green (`#0f2b20`), amber (`#f2c14e`), condensed display
type and Source Serif prose. Its working paths were Start, chapter playback, audience switch,
source inspection and receipt download. The first visual pass kept too many green panels,
repeated small uppercase labels and mixed-family headline emphasis. The stadium crowd also
competed with the action. Those were the patterns selected for replacement.

The redesign preserves the logo, routes, public APIs, navigation labels and form IDs. It adds
no framework or runtime component dependency. Theme preference is independent of match
preferences. Existing document titles and descriptions remain; no deployed search-ranking
baseline is available for this prototype.

## Decisions

- A real generated atmosphere image introduces the story. It is captioned as AI-generated,
  not represented as match footage. The asset was generated for this project, transcoded to
  a 157,116-byte WebP without changing its scene, and is served locally. Responsive 480px
  and 960px variants are 23,874 and 67,128 bytes. The browser selects by width and pixel density.
- One plain sans-serif headline, short supporting copy and one primary action. The visual
  entrance disappears when playback starts, leaving a compact title and chapter navigation.
- Light and dark themes follow the operating system, with a manual preference. Each mode
  has one page-wide palette; media and team-data colors retain their semantic meanings.
- The story sits beside the pitch without an extra card. Source inspection and alternate
  endings use distinct compositions. Only the entrance has an uppercase section eyebrow.
- Citron identifies interaction and evidence. It uses dark olive for readable accent text on
  light surfaces. Controls and media use a 4px radius; editorial groups are square.
- Entrance motion establishes hierarchy; the selected-story transition acknowledges a
  chapter change. Motion uses opacity/transform and respects reduced motion. No scroll hijack.
- Three.js and stadium assets load only when Judge Mode starts. The full app retains its
  automatic broadcast initialization. The judge crowd is darker and less saturated so the
  action and overlays remain the visual focus.
- The evidence map is an actual data visualization. Its pitch lines and source endpoints
  are functional geometry, not decorative grid art. Model comparison bars encode outcomes.

## Verification scope

The browser journey checks real replay, chapter locking, selected-versus-latest behavior,
source geometry, receipt download, keyboard focus, failed and delayed requests, alternate
endings and independent mobile sessions. It also checks the initial theme and absence of
the 3D module before Start. Separate visual checks cover both themes, 320/390/768px layouts,
headline and action fit, focus visibility, contrast and reduced motion.

Lighthouse 13.5.0, headless Chromium, mobile defaults, localhost `/judge`, 26 October 2026
([machine-readable measurements](presentation-audit.json)):

| Metric | Final local run |
|---|---|
| Performance | 96 / 100 |
| Automated accessibility | 100 / 100 |
| First contentful paint | 1.7 s |
| Largest contentful paint | 2.7 s |
| Cumulative layout shift | 0 |
| Total blocking time | 10 ms |

The first pass scored 83/98. Responsive images, compressed responses, deferred application
scripts, earlier entrance rendering, font preloads and a correct initial main landmark
addressed the observed problems. The main landmark moves to the match stage during playback.
The browser journey verifies that SSE is not gzip-compressed, so match events remain unbuffered.
The final checks passed all 80 Python tests, six JavaScript contracts and the complete browser
journey. Chart legends use readable neutral text while their swatches retain team colors.

These are local lab measurements of the entrance, not field performance or a full accessibility
certification. LCP remains above the 2.5-second target; deployment caching and network/device
measurements are still needed. Lighthouse also flags image delivery and cache lifetimes.
The 3D replay needs separate device testing; no mobile frame-rate or field INP claim is made.

## Asset provenance

`web/assets/matchday-hero.webp` is an original generated scene: a fictional football and
anonymous player under floodlights. It uses no league, club, sponsor or identifiable-person
assets. The existing 3D models and fonts retain their prior licenses. The hero is atmosphere;
all interactive match explanations continue to come from the synthetic event pipeline.
