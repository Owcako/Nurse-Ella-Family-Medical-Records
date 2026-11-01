import {useEffect, useRef} from 'react'
import './recording-tap-indicator.css'

// Recording is an opt-in presentation setting, independent of demo mode.
// Keep document listeners and transient DOM outside the medical workflows.
export function RecordingTapIndicator ({enabled}: {enabled: boolean})
{
  const overlay = useRef<HTMLDivElement> (null)

  useEffect (() => {
    if (!enabled) return
    const host = overlay.current!
    const rings = new Map<HTMLDivElement, () => void> ()
    const reducedMotion = window.matchMedia ('(prefers-reduced-motion: reduce)')
    let frame = 0

    function promote ()
    {
      if (!rings.size || typeof host.showPopover !== 'function') return
      try
      {
        if (host.matches (':popover-open')) host.hidePopover ()
        host.showPopover ()
      }
      catch
      {
        // Older browsers still get a body overlay without affecting input.
        host.removeAttribute ('popover')
      }
    }

    function schedulePromotion ()
    {
      cancelAnimationFrame (frame)
      frame = requestAnimationFrame (promote)
    }

    function pressed (event: PointerEvent)
    {
      if (!event.isPrimary || event.button !== 0) return
      if (rings.size >= 16) rings.values ().next ().value?. ()
      const ring = document.createElement ('div')
      ring.className = 'recording-tap-ring'
      ring.style.left = `${event.clientX}px`
      ring.style.top = `${event.clientY}px`
      host.append (ring)
      const animation = ring.animate ([
        {transform: `translate(-50%, -50%) scale(${reducedMotion.matches ? 1 : 0})`, opacity: 1},
        {transform: 'translate(-50%, -50%) scale(1)', opacity: 0},
      ], {duration: 1000, easing: 'ease-out', fill: 'forwards'})
      const timer = window.setTimeout (remove, 1000)

      function remove ()
      {
        window.clearTimeout (timer)
        animation.cancel ()
        ring.remove ()
        rings.delete (ring)
      }

      rings.set (ring, remove)
      promote ()
      // A target handler may open a dialog after this capture listener runs.
      schedulePromotion ()
    }

    function layerChanged (event: Event)
    {
      if (event.target instanceof HTMLElement && event.target !== host &&
        (event.target instanceof HTMLDialogElement || event.target.hasAttribute ('popover')))
        schedulePromotion ()
    }

    if (typeof host.showPopover !== 'function') host.removeAttribute ('popover')
    document.addEventListener ('pointerdown', pressed, {capture: true, passive: true})
    document.addEventListener ('click', schedulePromotion, {capture: true, passive: true})
    document.addEventListener ('toggle', layerChanged, true)

    return () => {
      document.removeEventListener ('pointerdown', pressed, true)
      document.removeEventListener ('click', schedulePromotion, true)
      document.removeEventListener ('toggle', layerChanged, true)
      cancelAnimationFrame (frame)
      for (const remove of rings.values ()) remove ()
      if (host.hasAttribute ('popover') && host.matches (':popover-open')) host.hidePopover ()
    }
  }, [enabled])

  return enabled ? <div ref={overlay} className="recording-tap-overlay" popover="manual" aria-hidden="true" /> : null
}
