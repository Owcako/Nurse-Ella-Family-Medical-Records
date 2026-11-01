import {Button} from '@chakra-ui/react'
import {useEffect, useRef} from 'react'
import type {MedicalFile, Profile} from '../import/types'
import type {Labels} from '../import/strings'
import {memberIdentity} from './browsing'

// Management is a secondary dialog, separate from the active member filter.
// Child edit/confirmation dialogs remain explicit and do not close this list.
export function MemberManager ({profiles, files, labels: t, language, busy, error, onAdd, onEdit, onRemove, onClose}: {
  profiles: Profile[]; files: MedicalFile[]; labels: Labels; language: 'en' | 'zh'; busy: boolean; error: string
  onAdd: () => void; onEdit: (profile: Profile) => void; onRemove: (profile: Profile) => void; onClose: () => void
})
{
  const dialog = useRef<HTMLDialogElement> (null)
  const zh = language === 'zh'
  useEffect (() => {
    const previous = document.activeElement
    const element = dialog.current!
    element.showModal ()
    return () => {element.close (); if (previous instanceof HTMLElement && previous.isConnected) previous.focus ()}
  }, [])
  return <dialog ref={dialog} className="modal member-manager" aria-labelledby="member-manager-title" onCancel={event => {event.preventDefault (); if (!busy) onClose ()}}>
    <header className="member-manager-heading"><h2 id="member-manager-title">{zh ? '管理成员' : 'Manage members'}</h2><Button unstyled disabled={busy} onClick={onClose}>{t.close}</Button></header>
    <div className="member-manager-body">
      <p className="member-manager-help">{zh ? '在这里新增、修改或移除家庭成员。移除成员不会删除病历。' : 'Add, update or remove family members here. Removing a member keeps their records.'}</p>
      <Button unstyled className="primary" disabled={busy} onClick={onAdd}>＋ {t.addMember}</Button>
      {error && <p role="alert" className="notice error">{error}</p>}
      {profiles.length === 0 && <p className="member-manager-help">{zh ? '还没有家庭成员。' : 'No family members yet.'}</p>}
      <div className="member-manager-list">{profiles.map (profile => <article className="managed-member" key={profile.id}>
        <strong>{profile.name}</strong><small>{files.filter (file => memberIdentity (file, profiles) === `profile:${profile.id}`).length} {zh ? '份病历' : 'records'}</small>
        {profile.aliases.length > 0 && <p>{zh ? '报告中的姓名' : 'Also recorded as'}: {profile.aliases.join (', ')}</p>}
        <div className="managed-member-actions"><Button unstyled disabled={busy} onClick={() => onEdit (profile)}>{t.editMember}</Button><Button unstyled className="danger" disabled={busy} onClick={() => onRemove (profile)}>{t.removeMember}</Button></div>
      </article>)}</div>
    </div>
  </dialog>
}
