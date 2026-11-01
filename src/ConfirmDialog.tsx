import {Button} from '@chakra-ui/react'
import {useEffect, useId, useRef} from 'react'
import './dialogs.css'

export type Confirmation = {
  title: string; message: string; confirmLabel: string; cancelLabel: string; destructive?: boolean
}

// View: src/import/ui-flow.svg#U17
// Native HTML dialogs render inside the app, trap focus, and make the background
// inert. Default focus is Cancel; Escape cancels without invoking the action.
export function ConfirmDialog ({title, message, confirmLabel, cancelLabel, destructive, onChoice}: Confirmation & {onChoice: (accepted: boolean) => void})
{
  const dialog = useRef<HTMLDialogElement> (null)
  const id = useId ()
  useEffect (() => {
    const element = dialog.current!
    const previous = document.activeElement
    element.showModal ()
    return () => {
      element.close ()
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus ({preventScroll: true})
    }
  }, [])

  return <dialog ref={dialog} className="modal profile-dialog confirmation-dialog" aria-labelledby={`${id}-title`} aria-describedby={`${id}-message`}
    onCancel={event => {event.preventDefault (); onChoice (false)}}>
    <header className="confirmation-dialog-header"><h2 id={`${id}-title`}>{title}</h2></header>
    <div className="confirmation-dialog-content"><p id={`${id}-message`}>{message}</p></div>
    <div className="dialog-actions">
      <Button unstyled type="button" className="dialog-cancel" autoFocus onClick={() => onChoice (false)}>{cancelLabel}</Button>
      <Button unstyled type="button" className={`primary dialog-confirm${destructive ? ' destructive' : ''}`} onClick={() => onChoice (true)}>{confirmLabel}</Button>
    </div>
  </dialog>
}
