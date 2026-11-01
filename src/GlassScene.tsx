import {useEffect, useRef} from 'react'
import {LiquidGlass} from '@ybouane/liquidglass'

// Only the decorative scene is captured. Reports and conversation text never
// enter the shader's DOM rasterizer. All surfaces share one WebGL context.
// View: src/import/ui-flow.svg#U14
// Capture only decorative surfaces in one WebGL scene, never patient/chat content.
// Observers align it with panels; reduced motion or WebGL failure keeps the CSS fallback.
export function GlassScene ()
{
  const root = useRef<HTMLDivElement> (null)
  useEffect (() => {
    const scene = root.current!
    const panels = ['.library-pane', '.chat-shell', '.library-pane .panel-toggle', '.chat-shell .panel-toggle']
    const surfaces = Array.from (scene.querySelectorAll<HTMLElement> ('.glass-surface'))
    let instance: LiquidGlass | undefined
    let disposed = false
    // View: src/import/ui-flow.svg#U14
    // Mirror panel rectangles onto decorative surfaces. This observes geometry, not report contents.
    function sync ()
    {
      surfaces.forEach ((surface, index) => {
        const target = document.querySelector<HTMLElement> (panels[index])
        const rect = target?.getBoundingClientRect ()
        surface.style.display = rect?.width && rect.height ? 'block' : 'none'
        if (!rect) return
        Object.assign (surface.style, {left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`})
      })
      instance?.markChanged ()
    }
    sync ()
    const observer = new ResizeObserver (sync)
    for (const selector of panels)
    {
      const target = document.querySelector (selector)
      if (target) observer.observe (target)
    }
    window.addEventListener ('resize', sync)
    const media = window.matchMedia ('(prefers-reduced-motion: reduce)')
    // View: src/import/ui-flow.svg#U14
    // Skip animation for reduced motion and destroy a late-created instance after unmount.
    // Always release observers, frame callbacks and GPU resources in effect cleanup.
    async function start ()
    {
      // CSS frosting remains available when WebGL is absent or motion is reduced.
      if (media.matches) return
      try
      {
        const glass = await LiquidGlass.init ({root: scene, glassElements: surfaces})
        if (disposed) glass.destroy ()
        else {instance = glass; sync ()}
      }
      catch {scene.dataset.fallback = 'true'}
    }
    const frame = requestAnimationFrame (() => void start ())
    return () => {disposed = true; cancelAnimationFrame (frame); observer.disconnect (); window.removeEventListener ('resize', sync); instance?.destroy ()}
  }, [])

  return <div ref={root} className="glass-scene" aria-hidden="true">
    <div className="hospital-floor" />
    {[0, 1, 2, 3].map (index => <div key={index} className="glass-surface" data-config={JSON.stringify ({
      blurAmount: index < 2 ? 0.32 : 0.16, refraction: index < 2 ? 0.09 : 0.035,
      chromAberration: index < 2 ? 0.012 : 0.005, distortion: 0.008, cornerRadius: index < 2 ? 24 : 10,
      zRadius: index < 2 ? 9 : 3, edgeHighlight: 0.12, fresnel: 0.16, tintStrength: 0.015,
      saturation: -0.08, brightness: 0.025, shadowOpacity: 0.08, shadowSpread: 5,
      floating: false, button: index >= 2,
    })} />)}
  </div>
}
