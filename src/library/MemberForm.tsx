import {Button, Input} from '@chakra-ui/react'
import {useEffect, useRef, useState} from 'react'
import {json, request} from '../import/api'
import type {Profile} from '../import/types'
import type {Labels} from '../import/strings'
import {Loading} from '../Loading'

export type MemberDraft = {profile?: Profile; detectedName?: string}

// View: src/import/ui-flow.svg#U13
// Edit managed names and aliases in an explicit dialog. These profiles organize
// reports; they are not user logins or permission boundaries.
export function MemberForm ({draft, labels: t, onSaved, onClose}: {
  draft: MemberDraft; labels: Labels; onSaved: (profile: Profile) => void; onClose: () => void
})
{
  const dialog = useRef<HTMLDialogElement> (null)
  const [name, setName] = useState (draft.profile?.name ?? draft.detectedName ?? '')
  const [aliases, setAliases] = useState (draft.profile?.aliases.join (', ') ?? '')
  const [busy, setBusy] = useState (false)
  const [error, setError] = useState ('')
  useEffect (() => {dialog.current?.showModal ()}, [])

  // View: backend/library-storage.svg#S8
  // Keep the reviewed printed name as an alias when the display name differs.
  // Wait for server alias-conflict validation and receipt before closing the form.
  async function save ()
  {
    setBusy (true)
    setError ('')
    const values = aliases.split (',').map (value => value.trim ()).filter (Boolean)
    // Retain the reviewed printed name as an alias when a different display name
    // is chosen. The backend links the preserved evidence without rewriting text.
    if (draft.detectedName && draft.detectedName !== name.trim () && !values.includes (draft.detectedName)) values.push (draft.detectedName)
    try
    {
      const profile = await request<Profile> (draft.profile ? `/profiles/${draft.profile.id}` : '/profiles', {
        method: draft.profile ? 'PUT' : 'POST', ...json ({name: name.trim (), aliases: values}),
      })
      onSaved (profile)
    }
    catch (error) {setError ((error as Error).message); setBusy (false)}
  }

  return <dialog ref={dialog} className="modal profile-dialog" aria-labelledby="member-form-title" onCancel={event => {if (busy) event.preventDefault (); else onClose ()}}>
    <h2 id="member-form-title">{draft.profile ? t.editMember : t.addMember}</h2>
    {draft.detectedName && <p>{t.detectedMember}: <strong>{draft.detectedName}</strong>. {t.newMemberHelp}</p>}
    <form className="loading-region" aria-busy={busy} onSubmit={event => {event.preventDefault (); void save ()}}>
      {busy && <Loading overlay label={t.saving} />}
      <label>{t.name}<Input unstyled autoFocus disabled={busy} value={name} maxLength={100} onChange={event => setName (event.target.value)} /></label>
      <label>{t.aliases}<Input unstyled disabled={busy} value={aliases} onChange={event => setAliases (event.target.value)} /></label>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="actions"><Button unstyled className="primary" type="submit" disabled={busy || !name.trim ()}>{busy ? t.saving : draft.profile ? t.editMember : t.addMember}</Button><Button unstyled type="button" disabled={busy} onClick={onClose}>{t.cancel}</Button></div>
    </form>
  </dialog>
}
