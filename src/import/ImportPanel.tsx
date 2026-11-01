import {Button, Input, Textarea} from '@chakra-ui/react'
import {useEffect, useImperativeHandle, useRef, useState} from 'react'
import type {Ref} from 'react'
import {json, operationKey, request} from './api'
import type {Configuration, MedicalFile} from './types'
import type {Labels} from './strings'
import {Spinner} from '../Loading'
import {useConfirmation} from '../useConfirmation'

type Action = {kind: 'files'; files: File[]; keys: string[]} | {kind: 'text'; text: string; title: string; key: string}
export type ImportPanelHandle = {open: () => void}

// Architecture: ui-flow.svg#U1 (picker), #U2 (local draft).
// View: src/import/ui-flow.svg#U1
// Own file picking, optional text drafts and retryable submission state.
// Original storage and AI work begin only when a file is chosen or a text draft is saved.
export function ImportPanel ({ref, config, labels: t, onStored, onDirty, onBusy}: {
  ref?: Ref<ImportPanelHandle>
  config: Configuration; labels: Labels; onStored: (file: MedicalFile) => void; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void
})
{
  const input = useRef<HTMLInputElement> (null)
  const menu = useRef<HTMLDetailsElement> (null)
  const [accept, setAccept] = useState ('')
  const [editing, setEditing] = useState (false)
  const [title, setTitle] = useState ('')
  const [text, setText] = useState ('')
  const [action, setAction] = useState<Action | null> (null)
  const [busy, setBusy] = useState (false)
  const [error, setError] = useState ('')
  const confirmation = useConfirmation ()
  const pendingRequest = useRef<AbortController | null> (null)
  useImperativeHandle (ref, () => ({open: () => {
    if (busy || !menu.current) return
    menu.current.open = true
    menu.current.scrollIntoView ({block: 'nearest'})
    menu.current.querySelector<HTMLButtonElement> ('.import-actions button')?.focus ({preventScroll: true})
  }}))
  useEffect (() => {onBusy (busy)}, [busy, onBusy])

  // View: src/import/ui-flow.svg#U15
  // Reset remounts this panel. Abort pending submissions and stop the multi-file
  // loop so it cannot continue uploading the previous demo's files after reset.
  useEffect (() => () => pendingRequest.current?.abort (), [])

  // View: src/import/ui-flow.svg#U1
  // Set accepted extensions on the real browser picker before opening it; the server
  // still validates media and size because picker filters are not a trust boundary.
  function pick (formats: string)
  {
    if (menu.current) menu.current.open = false
    // ui-flow.svg#U1: use the browser picker; each selected file stays independent.
    setAccept (formats)
    if (input.current)
    {
      input.current.accept = formats
      input.current.click ()
    }
  }

  // View: src/import/ui-flow.svg#U3
  // Submit directly without a processing-confirmation prompt. Keep stable operation
  // keys and failed action payloads so an uncertain network result can be retried safely.
  async function submit (next: Action)
  {
    // View: src/import/ui-flow.svg#U4
    // Retain the exact failed action and operation keys until the backend confirms storage.
    // Upload retry is safe even when the first response was lost after the original committed.
    setBusy (true)
    setError ('')
    setAction (next)
    const controller = new AbortController ()
    pendingRequest.current = controller
    // ui-flow.svg#U4: retain operation keys across retries, including uncertain responses.
    try
    {
      if (next.kind === 'files')
      {
        for (let i = 0; i < next.files.length; i++)
        {
          if (controller.signal.aborted) return
          const body = new FormData ()
          body.append ('file', next.files[i])
          onStored (await request<MedicalFile> ('/imports', {method: 'POST', body, signal: controller.signal, headers: {'Idempotency-Key': next.keys[i]}}))
        }
      }
      else
      {
        // ui-flow.svg#U2: new text leaves draft state only after explicit Save is confirmed.
        const options = json ({title: next.title, text: next.text})
        onStored (await request<MedicalFile> ('/texts', {...options, method: 'POST', signal: controller.signal, headers: {...options.headers, 'Idempotency-Key': next.key}}))
        setEditing (false)
        setText ('')
        setTitle ('')
        onDirty (false)
      }
      setAction (null)
    }
    catch (error)
    {
      setError ((error as Error).message)
    }
    finally
    {
      if (pendingRequest.current === controller) pendingRequest.current = null
      setBusy (false)
    }
  }

  async function cancelDraft ()
  {
    if ((text || title) && !await confirmation.ask ({title: t.unsavedTitle, message: t.unsaved, confirmLabel: t.discard, cancelLabel: t.stay})) return
    setEditing (false)
    setTitle ('')
    setText ('')
    onDirty (false)
  }

  return <section className="import-card loading-region" aria-busy={busy}>
    <div className="busy-controls" inert={busy}>
    <details ref={menu} className="import-menu" onKeyDown={event => {if (event.key === 'Escape') {menu.current!.open = false; menu.current?.querySelector ('summary')?.focus ()}}}>
    <summary aria-label={t.add} title={t.add} aria-disabled={busy}>{busy ? <Spinner /> : '＋'}</summary>
    <div className="import-popover"><h3>{t.add}</h3><p className="intro">{t.intro}</p><div className="import-actions">
      <Button unstyled disabled={busy} onClick={() => pick ('.jpg,.jpeg,.png,.webp')}><span aria-hidden="true">▧</span>{t.photo}</Button>
      <Button unstyled disabled={busy} onClick={() => pick ('.pdf')}><span aria-hidden="true">▤</span>{t.pdf}</Button>
      <Button unstyled disabled={busy} onClick={() => pick ('.txt')}><span aria-hidden="true">≡</span>{t.textFile}</Button>
      <Button unstyled disabled={busy} onClick={() => {setEditing (true); menu.current!.open = false}}><span aria-hidden="true">＋</span>{t.newText}</Button>
    </div>
    <small>{t.limits}</small></div></details>
    <Input unstyled ref={input} type="file" hidden multiple accept={accept} onChange={event => {
      const files = Array.from (event.target.files ?? [])
      if (files.length) void submit ({kind: 'files', files, keys: files.map (() => operationKey ())})
      event.target.value = ''
    }} />
    {error && <div role="alert" className="notice error">{t.savingFailed}: {error}
      {action && <Button unstyled disabled={busy} onClick={() => void submit (action)}>{t.uploadRetry}</Button>}
    </div>}
    {editing && <div className="new-draft">
      <h2>{t.draft}</h2>
      <label>{t.title}<Input unstyled maxLength={200} value={title} disabled={busy} onChange={event => {setTitle (event.target.value); onDirty (true)}} /></label>
      <label>{t.text}<Textarea unstyled rows={8} maxLength={config.max_text} value={text} disabled={busy} onChange={event => {setText (event.target.value); onDirty (true)}} /></label>
      <div className="actions"><Button unstyled className="primary" disabled={busy || !title.trim () || !text.trim ()} onClick={() => void submit ({kind: 'text', title, text, key: action?.kind === 'text' && action.title === title && action.text === text ? action.key : operationKey ()})}>{busy ? t.saving : t.saveNew}</Button>
        <Button unstyled disabled={busy} onClick={() => void cancelDraft ()}>{t.cancel}</Button></div>
    </div>}
    </div>
    {confirmation.dialog}
  </section>
}
