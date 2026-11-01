import {formatDate} from '../dates'
import {Button} from '@chakra-ui/react'
import {Folder, FolderOpen, RefreshCw} from 'lucide-react'
import {Dropdown} from '../Dropdown'
import {Loading} from '../Loading'
import {useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {dimensions} from '../import/types'
import type {Dimension, MedicalFile, Profile} from '../import/types'
import type {Labels} from '../import/strings'
import {fileBranches, groupFiles, memberIdentity, memberOptions, needsAttention, needsMemberReview, unresolvedFields} from './browsing'
import type {FileBranch} from './browsing'

const browseDimensions: Dimension[] = ['member', 'department', 'date']

export type BrowseState = {dimension: Dimension; member: string; attention: boolean}

// View: src/library/browsing-flow.svg#R1
// Derive the member-filtered and optionally attention-filtered file set from saved
// snapshots. Grouping changes the view, not ownership or underlying clinical evidence.
export function LibraryBrowser ({files, profiles, labels: t, state, onChange, selected, onSelect, loading, error, onRefresh, onReviewMember, onManageMembers, onAddMember, onAddRecord, addingRecord, language}: {
  files: MedicalFile[]; profiles: Profile[]; labels: Labels; state: BrowseState; onChange: (state: BrowseState) => void
  selected: string | null; onSelect: (id: string) => void; loading: boolean; error: string; onRefresh: () => void
  onReviewMember: (file: MedicalFile) => void
  onManageMembers: () => void; onAddMember: () => void; language: 'en' | 'zh'
  onAddRecord?: () => void; addingRecord: boolean
})
{
  const tabs = useRef<HTMLDivElement> (null)
  const [expanded, setExpanded] = useState<Record<string, boolean>> ({})
  const options = memberOptions (profiles)
  const memberFiles = files.filter (file => state.dimension === 'member' || !state.member || memberIdentity (file, profiles) === state.member)
  const attentionCount = memberFiles.filter (file => needsAttention (file) || needsMemberReview (file, profiles)).length
  const visible = memberFiles.filter (file => !state.attention || needsAttention (file) || needsMemberReview (file, profiles))
  const groups = groupFiles (visible, state.dimension, profiles)
  const branches = fileBranches (groups, state.dimension)

  // View: src/library/browsing-flow.svg#R7
  // Render nested year/month/category branches with stable IDs and explicit expansion
  // state. Rows open a document by ID; count each document once inside a branch.
  function branch (group: FileBranch): ReactNode
  {
    const id = `${state.dimension}:${group.id}`
    const label = group.kind === 'unparsed-date' ? t.dateNeedsReview : group.kind === 'unknown-month' ? t.unknownMonth : group.kind === 'month' ? t.months[Number (group.value) - 1] :
      group.placement === 'unknown' ? (state.dimension === 'member' ? t.unassigned : t.unknown) : group.value
    return <details className={`file-group file-branch placement-${group.placement}`} key={id} open={expanded[id] ?? false}>
      <summary onClick={event => {event.preventDefault (); setExpanded (old => ({...old, [id]: !old[id]}))}}>
        <span className="branch-arrow" aria-hidden="true">›</span>{expanded[id] ? <FolderOpen className="branch-folder" aria-hidden="true" /> : <Folder className="branch-folder" aria-hidden="true" />}<span className="branch-label">{label}</span>
        {group.placement === 'tentative' && <span className="placement-badge">{t.tentative}</span>}<span className="branch-count">{group.files.length}</span>
      </summary>
      <div className="branch-contents">{group.children ? group.children.map (branch) : group.files.map (file => {
        const missing = unresolvedFields (file)
        const member = file.metadata?.member
        const date = file.metadata?.date
        const profile = profiles.find (profile => memberIdentity (file, profiles) === `profile:${profile.id}`)
        const review = needsMemberReview (file, profiles)
        return <div className="file-entry" key={file.id}><Button unstyled data-file-id={file.id} className={`file-row ${selected === file.id ? 'selected' : ''}`} onClick={() => onSelect (file.id)} aria-label={`${t.open}: ${file.title}`} aria-current={selected === file.id ? 'true' : undefined}>
          <span className="file-icon" aria-hidden="true">{file.media.startsWith ('image') ? '▧' : '▤'}</span>
          <span className="file-info"><strong>{file.title}</strong>
            <span className="record-tags"><span className="record-tag member-tag">{profile?.name ?? t.unassigned}</span><span className="record-tag date-tag">{date?.status === 'known' ? date.values.map (item => formatDate (item.value)).join (' / ') : `${t.date}: ${t.unknown}`}</span>
              {file.text_origin === 'demo_prepared' && <span className="record-tag prepared-tag">{t.demoPrepared}</span>}
              {file.metadata?.department.values.map (item => <span key={item.value} className="record-tag department-tag">{item.value}</span>)}
              {file.metadata?.disease.values.map (item => <span key={item.value} className="record-tag disease-tag">{item.value}</span>)}
              {(needsAttention (file) || review) && <span className="record-tag review-tag">{t.unresolved}</span>}</span>
            {member?.values.length && (!profile || profile.name !== member.values[0].value) ? <small>{t.detectedMember}: {member.values.map (item => item.value).join (' / ')}</small> : null}
            {review && <small className="unresolved-text">{t.memberReviewRequired}</small>}
            <small className={file.status === 'failed' ? 'error-text' : ''}>{t[file.status]}{file.status !== 'filed' ? ` · ${t[file.stage as keyof Labels] ?? file.stage}` : ''}</small>
            {missing.length > 0 && <small className="unresolved-text">{t.unresolvedFields}: {missing.map (key => `${t[key]} (${file.metadata?.[key].status === 'ambiguous' ? t.uncertainField : t.missingField})`).join (' · ')}</small>}
            {file.concerns.some (concern => !concern.reviewed) && <small className="unresolved-text">{t.concerns}: {file.concerns.filter (concern => !concern.reviewed).length}</small>}
            {file.check_status !== 'checked' && <small className="unresolved-text">{file.check_status === 'failed' ? t.checkFailed : t.stale}</small>}
            {file.extraction_status === 'failed' && <small className="error-text">{t.extraction}: {t.failed}</small>}
            {file.archive.index_state !== 'current' && <small className="unresolved-text">{t.indexPending}</small>}
            {file.metadata && dimensions.some (key => file.metadata![key].provenance === 'user_supplied') && <small>{t.supplied}</small>}
          </span><span aria-hidden="true">↗</span>
        </Button>{review && <Button unstyled className="review-member-button" onClick={() => onReviewMember (file)}>{t.reviewMember}: {file.title}</Button>}</div>
      })}</div>
    </details>
  }

  return <section aria-labelledby="library-title" className="library-browser">
    <div className="library-heading"><h2 id="library-title">{language === 'zh' ? '病历' : 'Records'} <span>{files.length}</span></h2>
      <Button unstyled className="refresh-records" aria-label={t.refresh} title={t.refresh} disabled={loading} onClick={onRefresh}><RefreshCw aria-hidden="true" /></Button>
    </div>
    <div className="library-heading-actions">
      <Button unstyled className="library-action" onClick={onManageMembers}>{language === 'zh' ? '管理成员' : 'Manage members'}</Button>
      {onAddRecord && <Button unstyled className="library-action primary" disabled={addingRecord} onClick={onAddRecord}>{language === 'zh' ? '添加病历' : 'Add record'}</Button>}
    </div>
    {!loading && !error && profiles.length === 0 && <aside className="member-onboarding"><p>{language === 'zh' ? '为家人建立档案，方便以后查找。也可以直接上传病历，稍后关联成员。' : 'Add a family member to organize their records. You can also upload first and link the member later.'}</p><Button unstyled className="primary" onClick={onAddMember}>{language === 'zh' ? '添加第一位家庭成员' : 'Add your first family member'}</Button></aside>}
    <div className="filters">
      {state.dimension !== 'member' && <div className="member-toolbar"><Dropdown className="member-filter" label={language === 'zh' ? '按家庭成员筛选' : 'Filter by family member'} showLabel value={state.member} onChange={member => onChange ({...state, member})}
        items={[{value: '', label: t.allMembers}, ...(state.member && !options.some (option => option.id === state.member) ? [{value: state.member, label: t.unavailableMember}] : []), ...options.map (option => ({value: option.id, label: option.name}))]} />
      </div>}
      <div className="segmented" aria-label={t.filter}>
        <Button unstyled aria-pressed={!state.attention} className={!state.attention ? 'active' : ''} onClick={() => onChange ({...state, attention: false})}>{t.all}</Button>
        <Button unstyled aria-pressed={state.attention} className={state.attention ? 'active' : ''} onClick={() => onChange ({...state, attention: true})}>{t.unresolved} <span>{attentionCount}</span></Button>
      </div>
    </div>
    <div ref={tabs} className="tabs browse-tabs" role="tablist" aria-label={t.library} onKeyDown={event => {
      const index = browseDimensions.indexOf (state.dimension)
      const next = event.key === 'ArrowRight' ? (index + 1) % browseDimensions.length : event.key === 'ArrowLeft' ? (index + browseDimensions.length - 1) % browseDimensions.length : event.key === 'Home' ? 0 : event.key === 'End' ? browseDimensions.length - 1 : -1
      if (next < 0) return
      event.preventDefault ()
      onChange ({...state, dimension: browseDimensions[next]})
      tabs.current?.querySelectorAll ('button')[next].focus ()
    }}>{browseDimensions.map (key => <Button unstyled id={`browse-${key}`} aria-controls="browse-results" role="tab" tabIndex={state.dimension === key ? 0 : -1} aria-selected={state.dimension === key} key={key} onClick={() => onChange ({...state, dimension: key})}>{t[key]}</Button>)}</div>
    <div id="browse-results" role="tabpanel" aria-labelledby={`browse-${state.dimension}`} aria-busy={loading} tabIndex={0}>
      {error && <div className="notice error" role="alert">{files.length ? t.readError : t.failedLoad} <p>{error}</p><Button unstyled onClick={onRefresh}>{t.refresh}</Button></div>}
      {loading ? <Loading center label={t.loading} /> : !files.length && !error ? <div className="empty"><div className="empty-symbol" aria-hidden="true">▤</div><h3>{t.empty}</h3><p>{t.emptyBody}</p></div> : !visible.length && !error ? <div className="empty" role="status"><h3>{t.noMatch}</h3><p>{t.emptyViewBody}</p>{(state.member || state.attention) && <Button unstyled onClick={() => onChange ({...state, member: '', attention: false})}>{t.clearFilters}</Button>}</div> : <>
        {state.attention && <p className="browse-context">{t.attentionHelp}</p>}
        <p className="result-count" role="status">{t.documents}: {visible.length} · {t[state.dimension]}: {branches.length}</p>
        <div className="file-tree">{branches.map (branch)}</div>
      </>}
    </div>
  </section>
}
