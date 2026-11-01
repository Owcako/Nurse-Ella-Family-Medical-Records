import {formatDate, parseDate} from '../dates'
import {DateFields} from './DateFields'
import {Button, Input, Textarea} from '@chakra-ui/react'
import {lazy, Suspense, useEffect, useId, useImperativeHandle, useRef, useState} from 'react'
import type {Ref} from 'react'
import {json, request} from './api'
import {dimensions} from './types'
import type {MedicalFile, Profile} from './types'
import type {Labels} from './strings'
import {memberIdentity, needsMemberReview} from '../library/browsing'
import {Loading} from '../Loading'
import {useConfirmation} from '../useConfirmation'

const PdfSource = lazy (() => import ('./PdfSource'))

function ProvenanceTag ({code, label}: {code: string; label: string})
{
  const id = useId ()
  const tip = useRef<HTMLDivElement> (null)
  return <>
    <Button unstyled className="provenance-tag" title={label} aria-label={label} aria-describedby={id} popoverTarget={id} onClick={event => {
      const rect = event.currentTarget.getBoundingClientRect ()
      if (tip.current)
      {
        tip.current.style.left = `${Math.max (8, Math.min (rect.left, window.innerWidth - 248))}px`
        tip.current.style.top = `${rect.bottom + 88 > window.innerHeight ? Math.max (8, rect.top - 80) : rect.bottom + 6}px`
      }
    }}>[{code}]</Button>
    <div ref={tip} id={id} popover="auto" role="tooltip" className="provenance-tip"><strong>[{code}]</strong> {label}</div>
  </>
}

export type ViewerHandle = {leave: (action: () => void) => void; openSaved: () => void}

// Architecture: ui-flow.svg#U9 (inspection), #U7/#U8/#U12 (explicit actions).
// View: AGENTS.svg#F3
// Keep editable fields and their baseline revision local to this document.
// Saved text, source preview and check outcomes are related views of one stable identity.
export function Viewer ({ref, file, profiles, labels: t, onUpdate, onDelete, onBack, onDirty, resolveMember, onResolveDone, onReviewMember}: {
  ref?: Ref<ViewerHandle>
  file: MedicalFile; profiles: Profile[]; labels: Labels; onUpdate: (file: MedicalFile) => void
  onDelete: () => void; onBack: () => void; onDirty: (dirty: boolean) => void
  resolveMember: boolean; onResolveDone: () => void; onReviewMember: () => void
})
{
  const [tab, setTab] = useState ('current')
  const [editing, setEditing] = useState (resolveMember)
  const [editRevision, setEditRevision] = useState (file.revision)
  const [text, setText] = useState (file.text ?? '')
  const [member, setMember] = useState (file.metadata?.member.values[0]?.value ?? '')
  const [date, setDate] = useState (file.metadata?.date.values[0]?.value ?? '')
  const [department, setDepartment] = useState (file.metadata?.department.values.map (item => item.value).join (', ') ?? '')
  const [disease, setDisease] = useState (file.metadata?.disease.values.map (item => item.value).join (', ') ?? '')
  const [busy, setBusy] = useState (false)
  const [busyLabel, setBusyLabel] = useState (t.saving)
  const [sourceLoaded, setSourceLoaded] = useState (false)
  const confirmation = useConfirmation ()
  const [error, setError] = useState ('')
  const [zoom, setZoom] = useState (100)
  const [textZoom, setTextZoom] = useState (100)
  const [baseline, setBaseline] = useState ({text, member, date, department, disease})
  const [pending, setPending] = useState<{action: (saved?: MedicalFile) => void | Promise<void>} | null> (null)
  const dialog = useRef<HTMLDialogElement> (null)
  const textInput = useRef<HTMLTextAreaElement> (null)
  const dirty = editing && (text !== baseline.text || member !== baseline.member || date !== baseline.date || department !== baseline.department || disease !== baseline.disease)
  const validDate = date === baseline.date || !date || Boolean (parseDate (date))
  const processing = file.status === 'pending' || file.status === 'processing'
  const profile = profiles.find (profile => memberIdentity (file, profiles) === `profile:${profile.id}`)
  const sourceUrl = `/api/files/${encodeURIComponent (file.id)}/original`
  const zoomLabel = tab !== 'source' ? t.textZoom : file.media === 'application/pdf' ? t.pdfZoom : t.zoom
  const zoomValue = tab !== 'source' ? textZoom : zoom
  const zoomMin = tab !== 'source' ? 80 : 50
  const zoomMax = tab !== 'source' ? 200 : 250
  const showZoom = tab !== 'source' || file.media.startsWith ('image/') || file.media === 'application/pdf'

  function changeZoom (value: number)
  {
    if (tab !== 'source') setTextZoom (value)
    else setZoom (value)
  }

  useEffect (() => {onDirty (dirty)}, [dirty, onDirty])
  useEffect (() => {
    if (pending) dialog.current?.showModal ()
    else dialog.current?.close ()
  }, [pending])

  // View: src/import/ui-flow.svg#U11
  // Defer navigation/check actions behind Save/Discard/Stay when the draft is dirty.
  // Keep the pending action until a successful save or explicit discard resolves it.
  function beforeAction (action: (saved?: MedicalFile) => void | Promise<void>)
  {
    if (busy) return
    if (dirty) setPending ({action})
    else action ()
  }

  useImperativeHandle (ref, () => ({leave: beforeAction, openSaved: () => setTab ('current')}))

  // View: src/import/ui-flow.svg#U7
  // Capture the exact saved revision and field baseline at edit time. Polling may
  // continue, but cannot silently replace this draft or its concurrency precondition.
  function beginEdit ()
  {
    // ui-flow.svg#U7: capture the exact saved revision being edited. Polling may
    // update props, but must not replace a draft or silently advance its version.
    setEditRevision (file.revision)
    setText (file.text ?? '')
    setMember (file.metadata?.member.values[0]?.value ?? '')
    setDate (file.metadata?.date.values[0]?.value ?? '')
    setDepartment (file.metadata?.department.values.map (item => item.value).join (', ') ?? '')
    setDisease (file.metadata?.disease.values.map (item => item.value).join (', ') ?? '')
    setBaseline ({text: file.text ?? '', member: file.metadata?.member.values[0]?.value ?? '', date: file.metadata?.date.values[0]?.value ?? '',
      department: file.metadata?.department.values.map (item => item.value).join (', ') ?? '', disease: file.metadata?.disease.values.map (item => item.value).join (', ') ?? ''})
    setTab ('current')
    setError ('')
    setEditing (true)
  }

  // View: src/import/ui-flow.svg#U7
  // Validate the date, submit current text/details with the original editor revision,
  // and clear dirty state only after a confirmed receipt. Retain local edits on failure.
  async function save ()
  {
    if (!validDate) {setError (t.invalidDate); return}
    // ui-flow.svg#U7: save the editor revision; retain the local draft on failure.
    setBusy (true)
    setBusyLabel (t.saving)
    setError ('')
    try
    {
      const updated = await request<MedicalFile> (`/files/${encodeURIComponent (file.id)}/manual`, {method: 'PUT', ...json ({
        revision: editRevision, text, member_name: member, date: date === baseline.date ? date : formatDate (date),
        department: department.split (',').map (value => value.trim ()).filter (Boolean),
        disease: disease.split (',').map (value => value.trim ()).filter (Boolean),
      })})
      onDirty (false)
      setEditing (false)
      onUpdate (updated)
      setPending (null)
      await pending?.action (updated)
    }
    catch (error) {setError ((error as Error).message)}
    finally {setBusy (false)}
  }

  // View: src/import/ui-flow.svg#U12
  // Send only a saved revision to explicit checking. A saved correction can be passed
  // through the pending action, ensuring the check never uses unsaved browser text.
  async function recheck (saved = file)
  {
    setBusy (true)
    setBusyLabel (t.checking)
    setError ('')
    try
    {
      const options = json ({revision: saved.revision})
      onUpdate (await request<MedicalFile> (`/files/${encodeURIComponent (saved.id)}/recheck`, {method: 'POST', ...options}))
    }
    catch (error) {setError ((error as Error).message)}
    finally {setBusy (false)}
  }

  // View: src/import/ui-flow.svg#U8
  // Resume processing for this stored identity instead of uploading another source.
  async function retry ()
  {
    // ui-flow.svg#U8: resume the same pending identity.
    setBusy (true)
    setBusyLabel (t.processing)
    setError ('')
    try
    {
      onUpdate (await request<MedicalFile> (`/files/${encodeURIComponent (file.id)}/retry`, {method: 'POST'}))
    }
    catch (error) {setError ((error as Error).message)}
    finally {setBusy (false)}
  }

  async function reviewConcern (index: number, reviewed: boolean)
  {
    setBusy (true)
    setBusyLabel (t.saving)
    setError ('')
    try
    {
      onUpdate (await request<MedicalFile> (`/files/${encodeURIComponent (file.id)}/concerns/${index}`, {
        method: 'PUT', ...json ({revision: file.revision, reviewed}),
      }))
    }
    catch (error) {setError ((error as Error).message)}
    finally {setBusy (false)}
  }

  function concernCard (concern: MedicalFile['concerns'][number], index: number)
  {
    return <blockquote key={index} className={concern.reviewed ? 'reviewed-concern' : undefined}>
      <q>{concern.quote}</q><small>{t.textLocation}: {concern.start + 1}–{concern.end}</small><p>{concern.reason}</p>
      <div className="actions concern-actions">
        {concern.reviewed ? <Button unstyled disabled={busy || processing || editing || file.check_status !== 'checked'} onClick={() => void reviewConcern (index, false)}>{t.reopenConcern}</Button> : <>
          <Button unstyled disabled={busy || processing || editing || file.check_status !== 'checked'} onClick={() => void reviewConcern (index, true)}>{t.keepOriginal}</Button>
          <Button unstyled disabled={busy || processing || editing} onClick={() => {
            beginEdit ()
            requestAnimationFrame (() => {
              textInput.current?.focus ()
              textInput.current?.setSelectionRange (concern.start, concern.end)
              textInput.current?.scrollIntoView ({block: 'center', behavior: 'smooth'})
            })
          }}>{t.modifyText}</Button>
        </>}
      </div>
    </blockquote>
  }

  // View: src/import/ui-flow.svg#U10
  // Confirm destruction and wait for the server before removing the document from UI state.
  async function remove ()
  {
    // ui-flow.svg#U9: name/confirm the target, then wait for backend deletion.
    if (!await confirmation.ask ({title: t.delete, message: `${t.deleteQuestion}\n\n${file.title}`, confirmLabel: t.delete, cancelLabel: t.cancel, destructive: true})) return
    setBusy (true)
    setBusyLabel (t.removing)
    setError ('')
    try
    {
      await request (`/files/${encodeURIComponent (file.id)}`, {method: 'DELETE'})
      onDirty (false)
      onDelete ()
    }
    catch (error) {setError ((error as Error).message)}
    finally {setBusy (false)}
  }

  return <section className="viewer loading-region" aria-busy={busy || processing}>
    {busy && <Loading overlay label={busyLabel} />}
    <div className="viewer-content" inert={busy}>
    <div className="viewer-heading-row"><Button unstyled className="back" disabled={busy} onClick={onBack}>← {t.back}</Button><span className={`record-status status-${file.status}`} role="status">{t[file.status]}</span></div>
    <h2>{file.title}</h2>

    <div className="viewer-toolbar">
      {!editing && <Button unstyled disabled={busy || processing} onClick={beginEdit}>{t.edit}</Button>}
      <Button unstyled className="primary" disabled={!editing || busy || !text.trim () || !validDate} onClick={() => void save ()}>{busy ? t.saving : t.save}</Button>
      <Button unstyled disabled={busy || processing || (!dirty && !file.text?.trim ())} onClick={() => beforeAction (saved => {setEditing (false); return recheck (saved)})}>{busy ? t.checking : t.recheck}</Button>
      <Button unstyled aria-pressed={tab === 'source'} onClick={() => setTab (tab === 'source' ? 'current' : 'source')}>{tab === 'source' ? t.current : t.source}</Button>
      {showZoom && <div className="zoom-controls" role="group" aria-label={zoomLabel}>
        <Button unstyled aria-label={`${zoomLabel} −`} disabled={busy || zoomValue <= zoomMin} onClick={() => changeZoom (Math.max (zoomMin, zoomValue - 10))}><span className="small-a" aria-hidden="true">A</span> −</Button>
        <Button unstyled className="zoom-percent" aria-label={`${t.resetZoom} ${zoomLabel}`} title={t.resetZoom} disabled={busy} onClick={() => changeZoom (100)}>{zoomValue}%</Button>
        <Button unstyled aria-label={`${zoomLabel} +`} disabled={busy || zoomValue >= zoomMax} onClick={() => changeZoom (Math.min (zoomMax, zoomValue + 10))}><span className="large-a" aria-hidden="true">A</span> +</Button>
      </div>}
    </div>
    {processing && <Loading center label={`${t.processingNote} ${t.stage}: ${t[file.stage as keyof Labels] ?? file.stage}`} />}
    {file.error && <div className="notice error" role="alert">{file.error}</div>}
    {file.extraction_error && file.extraction_error !== file.error && <div className="notice error" role="alert">{t.extraction}: {file.extraction_error}</div>}
    <dl className="classifications">{dimensions.map (dimension => {
      const field = file.metadata?.[dimension]
      const provenance = field?.provenance === 'user_supplied' ? {code: 'U', label: t.supplied} :
        field?.provenance === 'ai_classified' ? {code: 'AI', label: t.aiClassified} :
          field?.status === 'known' ? {code: 'P/D', label: t.printed} : {code: '?', label: t.unresolvedFields}
      return <div key={dimension}><dt>{t[dimension]}</dt><dd>{dimension === 'member' ? profile?.name ?? t.unassigned : field?.values.length ? field.values.map (value => dimension === 'date' ? formatDate (value.value) : value.value).join (' · ') : t.unknown}
        {(dimension !== 'disease' || field?.status === 'known') && <ProvenanceTag code={provenance.code} label={provenance.label} />}
        {dimension === 'member' && field?.values.length ? <small>{t.detectedMember}: {field.values.map (value => value.value).join (' · ')}</small> : null}
        {field?.provenance === 'ai_classified' && <details><summary>{t.classificationEvidence}</summary>{field.values.map ((value, index) => <p key={index}><q>{value.quote}</q></p>)}</details>}
        {field?.status === 'ambiguous' && <details><summary>{t.tentative}</summary>{field.candidates.map ((value, index) => <p key={index}>{value.value}<br /><q>{value.quote}</q></p>)}</details>}
      </dd></div>
    })}</dl>
    {file.metadata?.member.status === 'ambiguous' && <p className="notice">{t.ambiguous}</p>}
    {!editing && needsMemberReview (file, profiles) && <div className="notice"><p>{t.memberReviewRequired}</p><Button unstyled onClick={onReviewMember}>{t.reviewMember}</Button></div>}
    {tab === 'source' ? <div className="source-view">
      <a href={sourceUrl} target="_blank" rel="noreferrer">{t.source} ↗</a>
      {file.media.startsWith ('image/') ? <><div className="image-scroll loading-region">{!sourceLoaded && <Loading overlay label={t.loadingSource} />}<img src={sourceUrl} alt={file.title} style={{width: `${zoom}%`, maxWidth: 'none'}} onLoad={() => setSourceLoaded (true)} onError={() => {setSourceLoaded (true); setError (t.sourceError)}} /></div></> : file.media === 'application/pdf' ?
        <Suspense fallback={<Loading center label={t.loadingPdf} />}><PdfSource url={sourceUrl} labels={t} zoom={zoom} /></Suspense> : <div className="source-frame loading-region">{!sourceLoaded && <Loading overlay label={t.loadingSource} />}<iframe title={file.title} src={sourceUrl} onLoad={() => setSourceLoaded (true)} /></div>}
    </div> : <>{editing ? <div className="editor">
      <p>{t.manual}</p>
      {resolveMember && <p className="notice">{t.correctMemberHelp}</p>}
      <label>{t.member}<Input unstyled disabled={busy} value={member} list="member-names" maxLength={500} onChange={event => setMember (event.target.value)} /></label>
      <datalist id="member-names">{profiles.map (profile => <option key={profile.id} value={profile.name} />)}</datalist>
      <DateFields value={date} onChange={setDate} disabled={busy} labels={t} valid={validDate} />
      <label>{t.department}<Input unstyled disabled={busy} value={department} onChange={event => setDepartment (event.target.value)} /></label>
      <label>{t.disease}<Input unstyled disabled={busy} value={disease} onChange={event => setDisease (event.target.value)} /></label><small>{t.separator}</small>
      <label>{t.text}<Textarea ref={textInput} unstyled disabled={busy} aria-label={t.text} rows={14} value={text} style={{fontSize: `${13 * textZoom / 100}px`}} maxLength={100000} onChange={event => setText (event.target.value)} /></label>
      <div className="actions"><Button unstyled disabled={busy} onClick={() => {
        beforeAction (() => {
          setEditing (false)
          onDirty (false)
          onResolveDone ()
        })
      }}>{t.cancel}</Button></div>
    </div> : <><div className="text-provenance">{t[file.text_origin as 'imported' | 'ai_extracted' | 'user_entered' | 'user_edited' | 'demo_prepared']}</div><pre className="document-text" style={{fontSize: `${13 * textZoom / 100}px`}}>{file.text ?? t.noText}</pre></>}</>}
    {/* ../../backend/database-schema.svg#D2: keep archive details below the report, before text-check results. */}
    <div className="notice archive-context" aria-label={t.archive}>
      <strong>{t.archive}: {file.archive.title}</strong>
      <p>{profile?.name ?? t.unassigned} · {file.archive.date_label ? formatDate (file.archive.date_label) : t.unknown} · {file.archive.department_code} · {t.documents}: {file.archive.document_count}</p>
      {file.text_origin === 'demo_prepared' && <details className="demo-prepared-notice"><summary>{t.demoPrepared}</summary><p>{t.demoPreparedHelp}</p></details>}
      {file.archive.patient_status === 'conflict' && <p role="alert">{t.identityConflict}</p>}
      {file.archive.index_state !== 'current' && <p role="status">{t.indexPending}{file.archive.index_error && `: ${file.archive.index_error}`}</p>}
      <details className="provenance-legend"><summary>{t.labelMeanings}</summary><dl>
        <div><dt>[P/D]</dt><dd>{t.printed}</dd></div>
        <div><dt>[U]</dt><dd>{t.supplied}</dd></div>
        <div><dt>[AI]</dt><dd>{t.aiClassified}</dd></div>
        <div><dt>[?]</dt><dd>{t.unresolvedFields}</dd></div>
      </dl></details>
    </div>
    <div className="check-results" aria-live="polite">
      <h3>{file.check_status === 'checked' ? file.concerns.some (concern => !concern.reviewed) ? t.concerns : t.checked : file.check_status === 'failed' ? t.checkFailed : t.stale}</h3>
      {file.check_error && <p role="alert">{file.check_error}</p>}
      {file.check_status !== 'checked' && (file.concerns.length > 0 || file.checked_text_revision != null) && <p>{t.previousCheck}</p>}
      {file.concerns.map ((concern, index) => !concern.reviewed && concernCard (concern, index))}
      {file.concerns.some (concern => concern.reviewed) && <details className="reviewed-concerns"><summary>{t.reviewedConcerns} ({file.concerns.filter (concern => concern.reviewed).length})</summary>
        <p>{t.reviewedHelp}</p>{file.concerns.map ((concern, index) => concern.reviewed && concernCard (concern, index))}
      </details>}
      {file.check_status === 'checked' && !file.concerns.length && <p>{t.noConcerns}</p>}
    </div>
    {error && <div className="notice error" role="alert">{error}</div>}
    <div className="actions viewer-actions">
      {file.status === 'failed' && !editing && <Button unstyled disabled={busy} onClick={() => void retry ()}>{t.retry}</Button>}
      <Button unstyled className="danger" disabled={busy || editing} onClick={() => void remove ()}>{t.delete}</Button>
    </div>
    </div>
    {confirmation.dialog}
    <dialog ref={dialog} className="modal profile-dialog" aria-labelledby="unsaved-title" onCancel={event => {event.preventDefault (); if (!busy) setPending (null)}}>
      <h2 id="unsaved-title">{t.unsavedTitle}</h2><p>{file.title}</p><p>{t.unsavedChoice}</p>
      {busy && <Loading center label={busyLabel} />}
      {error && <p className="notice error" role="alert">{error}</p>}
      <div className="actions"><Button unstyled className="primary" disabled={busy || !text.trim () || !validDate} onClick={() => void save ()}>{t.saveContinue}</Button>
        <Button unstyled disabled={busy} onClick={() => {const action = pending?.action; setPending (null); setEditing (false); onDirty (false); action?. ()}}>{t.discardContinue}</Button>
        <Button unstyled disabled={busy} onClick={() => setPending (null)}>{t.stay}</Button></div>
    </dialog>
  </section>
}
