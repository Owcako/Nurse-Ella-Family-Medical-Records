import {useEffect, useRef, useState} from 'react'
import {ConfirmDialog} from './ConfirmDialog'
import type {Confirmation} from './ConfirmDialog'

// View: src/import/ui-flow.svg#U17
// Replace synchronous browser confirms with a reusable asynchronous decision.
// Resolve pending decisions as canceled on unmount so a stale component cannot
// continue a destructive action after navigation/reset removed its prompt.
export function useConfirmation ()
{
  const [pending, setPending] = useState<Confirmation | null> (null)
  const resolve = useRef<((accepted: boolean) => void) | null> (null)
  useEffect (() => () => {resolve.current?.(false); resolve.current = null}, [])

  function ask (confirmation: Confirmation)
  {
    return new Promise<boolean> (finish => {
      resolve.current?.(false)
      resolve.current = finish
      setPending (confirmation)
    })
  }

  function choose (accepted: boolean)
  {
    resolve.current?.(accepted)
    resolve.current = null
    setPending (null)
  }

  return {ask, dialog: pending ? <ConfirmDialog {...pending} onChoice={choose} /> : null}
}
