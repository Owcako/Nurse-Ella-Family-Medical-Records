import {LoaderCircle} from 'lucide-react'
import './loading.css'

// View: src/import/ui-flow.svg#U5
// Share an animated, decorative icon and a spoken status across network waits.
// Overlays accompany disabled/inert controls; background polling stays nonblocking.
export function Spinner ()
{
  return <LoaderCircle className="loading-spinner" aria-hidden="true" />
}

export function Loading ({label, center = false, overlay = false}: {label: string; center?: boolean; overlay?: boolean})
{
  return <span role="status" className={`loading-status${center ? ' loading-center' : ''}${overlay ? ' loading-overlay' : ''}`}><Spinner /><span>{label}</span></span>
}
