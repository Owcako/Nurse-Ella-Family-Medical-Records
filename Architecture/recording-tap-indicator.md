# App-wide recording tap indicator

Status: implemented in `src/RecordingTapIndicator.tsx`, `src/recording-tap-indicator.css`, and `src/main.tsx`.

## Objective and scope

When explicitly enabled through the launch URL, show an expanding ring where the user presses anywhere within the application document. Grow from radius 0 to 28 CSS pixels over 1,000 ms while fading out. This is a presentation aid for screen recordings and works in both normal and demo modes. It does not start, stop, or detect operating-system screen recording.

Proposed defaults: primary touch, mouse, and pen presses are supported on all viewport sizes; secondary mouse buttons and non-primary pointers are ignored. A press starting a scroll also produces a ring: the visualization represents contact, not proof of a completed click. Native browser UI, the operating-system keyboard and file picker, and embedded cross-origin documents are outside the document's event boundary.

## Verified repository structure

- `src/main.tsx` mounts React StrictMode, ChakraProvider, and App. This is the stable ownership point for a global presentation component.
- `src/App.tsx` owns medical workflows and the separate session-backed demoMode. No recording state should enter those workflows.
- `src/navigation.ts` routes through `#records`, `#chat`, and `#/files/<id>`; a query parameter before the hash is independent of these routes.
- `src/Dropdown.tsx` uses Chakra portals; dropdown positioners use z-index 20 in `src/workspace.css`.
- Native dialogs opened with showModal appear throughout the app, including `src/library/MemberReview.tsx` and `src/import/Viewer.tsx`. Their top-layer rendering must be accounted for.

## External control contract

Read `new URLSearchParams(window.location.search).get('rec') === 'true'` once at startup.

- `/?rec=true#records` enables the indicator.
- `/?rec=false#records`, a missing parameter, or any other value disables it.
- Load or reload the URL to change the setting. In-app hash navigation preserves the current setting.
- No localStorage, sessionStorage, backend flag, build-time environment variable, or in-app control is required. The URL alone determines the behavior on each load, avoiding an accidentally persistent recording setting.
- Keep unrelated query parameters and the hash when constructing recording links.

The internal name should be `showTapIndicators`, since this flag only controls visualization. This public opt-in flag grants no permissions and must never gate sensitive operations. No automatic phone detection is necessary: recording intent is explicit.

## Proposed components and contracts

Add `src/RecordingTapIndicator.tsx` and `src/recording-tap-indicator.css`. Mount a single instance alongside App under the existing root in `src/main.tsx`, passing the startup boolean as `enabled`. App and individual buttons do not receive new props or handlers.

RecordingTapIndicator owns:

1. A passive, capture-phase document `pointerdown` listener while enabled. Capture observes presses before component handlers can stop bubbling. Never preventDefault, stop propagation, or capture the pointer.
2. Transient rings identified independently, with immutable viewport coordinates from clientX/clientY. Each press creates one ring; overlapping rings finish independently. No medical data, target text, or interaction history is recorded or transmitted.
3. A fixed viewport overlay with pointer-events none on its host, descendants, and backdrop; aria-hidden true; no focusable content or autofocus. Animate CSS transform and opacity through the Web Animations API rather than per-frame React state. This keeps animation timelines independent of top-layer reordering. Each ring is centered on its original contact point and removed after one second by a cleanup timer. Cap concurrent rings at 16, dropping the oldest if necessary.
4. Listener, animation, timer, and host cleanup on disable or unmount. Setup/cleanup must be symmetric under React StrictMode.

## Layering contract

Use a decorative `popover="manual"` overlay promoted with showPopover to the browser top layer. Reset its default margins, border, padding, and background; give it fixed inset 0 and viewport dimensions. It must not introduce modal behavior, focus changes, backdrop tint, or light-dismiss behavior.

Promote the overlay when creating a ring. If a press opens a native dialog later in the same interaction, re-promote the overlay after that dialog is shown so the active ring remains visible. Centralize this synchronization in the indicator, using capture-phase native dialog toggle observation and a scheduled frame; cancel scheduled work on cleanup. Do not modify every dialog or replace showModal. A native dialog can otherwise cover a body portal regardless of its z-index.

Feature-detect showPopover. On an unsupported browser, use the fixed body overlay as a graceful fallback, accepting that native modal dialogs may cover it. Target-phone verification must establish top-layer support before calling the feature complete for that device.

For prefers-reduced-motion, show a stationary ring for the same bounded lifetime rather than expanding it. Keep the visual configurable through CSS constants; the proposed initial style is a 3 px high-contrast outline with a subtle contrasting shadow for light and dark content.

## Normal flow and failure behavior

Launch recording URL -> startup boolean -> enabled global indicator -> document pointerdown -> viewport-coordinate ring -> normal target handler opens menu -> ring grows/fades for one second -> ring is removed. Hash navigation and demo-mode switches do not unmount the indicator.

When disabled, no overlay or pointer listener is installed. Overlay initialization or promotion failures must leave ordinary interactions working; fall back to the body overlay. Closing a menu, changing page, or opening a dialog must not restart a ring's lifetime. Multiple touches produce only the primary-pointer indication; gestures and scrolling retain their native behavior.

## Implementation handoff and completion evidence

Only root composition and the two new presentation files need to change. No new dependency or backend work is expected. The radius, color, scroll-start behavior, and reduced-motion adaptation above are proposed defaults rather than additional user requirements.

Verify on the actual phone recording: tapping the menu trigger shows a centered ring as the menu opens; taps on portal menu items and inside native dialogs are visible; scrolling and input focus still work; the keyboard does not intercept app taps; rings clean up after rapid presses; hash navigation and both demo settings preserve the flag; missing/false rec produces no rings. Verify reload enables/disables the flag. Run the existing frontend build and lint after implementation, with a focused browser check for URL activation, portal/dialog layering, event pass-through, and cleanup.

## Platform references

- Pointer events: https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events
- Popover top-layer behavior: https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/showPopover
- Manual popovers: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/popover
