import {Button} from '@chakra-ui/react'
import {useEffect, useRef} from 'react'
import type {MedicalFile} from '../import/types'
import type {Labels} from '../import/strings'

// View: src/library/browsing-flow.svg#R5
// Offer correction, a new profile, or deferral for an unmatched documented name.
// Do not resolve identity automatically merely to make the library tree look complete.
export function MemberReview ({file, labels: t, onMistake, onNew, onLater}: {
  file: MedicalFile; labels: Labels; onMistake: () => void; onNew: () => void; onLater: () => void
})
{
  const dialog = useRef<HTMLDialogElement> (null)
  useEffect (() => {dialog.current?.showModal ()}, [])
  return <dialog ref={dialog} className="modal profile-dialog" aria-labelledby="member-review-title" onCancel={onLater}>
    <h2 id="member-review-title">{t.reviewMember}</h2>
    <p><strong>{file.title}</strong></p>
    <p className="detected-member">{t.detectedMember}: <strong>{file.metadata?.member.values[0]?.value}</strong></p>
    <p>{t.memberQuestion}</p>
    <div className="actions"><Button unstyled onClick={onMistake}>{t.memberMistake}</Button><Button unstyled className="primary" onClick={onNew}>{t.memberNew}</Button><Button unstyled onClick={onLater}>{t.reviewLater}</Button></div>
  </dialog>
}
