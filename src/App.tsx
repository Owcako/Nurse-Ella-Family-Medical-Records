import {formatDate} from './dates'
import {Button} from '@chakra-ui/react'
import {FlaskConical} from 'lucide-react'
import {useCallback, useEffect, useRef, useState} from 'react'
import {ImportPanel} from './import/ImportPanel'
import type {ImportPanelHandle} from './import/ImportPanel'
import {Viewer} from './import/Viewer'
import type {ViewerHandle} from './import/Viewer'
import {json, request} from './import/api'
import {strings} from './import/strings'
import {dimensions} from './import/types'
import type {Configuration, MedicalFile, Profile} from './import/types'
import {LibraryBrowser} from './library/LibraryBrowser'
import type {BrowseState} from './library/LibraryBrowser'
import {MemberForm} from './library/MemberForm'
import type {MemberDraft} from './library/MemberForm'
import {MemberReview} from './library/MemberReview'
import {MemberManager} from './library/MemberManager'
import {canonicalHash, fileFromHash, pageFromHash} from './navigation'
import type {Page} from './navigation'
import {memberReviewKey, needsMemberReview} from './library/browsing'
import './App.css'
import {ChatPanel} from './chat/ChatPanel'
import {Workspace} from './Workspace'
import {GlassScene} from './GlassScene'
import {Dropdown} from './Dropdown'
import './workspace.css'
import {DemoNotice} from './DemoNotice'
import {Loading} from './Loading'
import {useConfirmation} from './useConfirmation'
import './dialogs.css'
import './demo-mode.css'
import './library/members.css'
import './mobile-compact.css'
import {demoDocuments as currentDemoDocuments, isLiveDemoFile} from './demo'
import {DemoSamplePicker, DemoWelcome} from './DemoExperience'

// View: src/import/ui-flow.svg#U6
// Restore only supported browse dimensions/member filters from this browser session.
// This restores navigation, not an authoritative record snapshot.
function savedBrowseState (): BrowseState
{
  const saved = new URLSearchParams (sessionStorage.getItem ('libraryBrowse') ?? '')
  const dimension = dimensions.find (key => key !== 'disease' && key === saved.get ('view')) ?? 'member'
  return {dimension, member: saved.get ('member') ?? '', attention: saved.get ('attention') === 'true'}
}

// View: src/import/ui-flow.svg#U6
// Decode a stable document ID from the hash. Invalid escaping must not crash navigation.
// These IDs belong only to this tab, never to the shared library or localStorage.
function savedUploads (key = 'pendingUploads'): Set<string>
{
  try
  {
    const ids: unknown = JSON.parse (sessionStorage.getItem (key) ?? '[]')
    return new Set (Array.isArray (ids) ? ids.filter ((id): id is string => typeof id === 'string') : [])
  }
  catch {return new Set ()}
}

// Architecture: ../implementation-architecture.svg#O1; UI stages: import/ui-flow.svg.
// View: implementation-architecture.svg#O1
// Compose Library, Viewer and Chat around shared snapshots and one member filter.
// Keep local drafts/navigation state separate from backend-confirmed document receipts.
function App ()
{
  const [language, setLanguage] = useState<'en' | 'zh'> (() => localStorage.getItem ('language') === 'zh' ? 'zh' : 'en')
  const [demoAcknowledged, setDemoAcknowledged] = useState (false)
  const [demoMode, setDemoMode] = useState (() => sessionStorage.getItem ('appMode') === 'demo')
  const [demoBusy, setDemoBusy] = useState (false)
  const [demoWelcome, setDemoWelcome] = useState (false)
  const [samplePicker, setSamplePicker] = useState (false)
  const [demoError, setDemoError] = useState ('')
  const t = strings[language]
  const confirmation = useConfirmation ()
  const [config, setConfig] = useState<Configuration | null> (null)
  const [files, setFiles] = useState<MedicalFile[]> ([])
  const [profiles, setProfiles] = useState<Profile[]> ([])
  const [route, setRoute] = useState (() => canonicalHash (location.hash))
  const page = pageFromHash (route)
  const showReport = Boolean (fileFromHash (route))
  const [selected, setSelected] = useState<string | null> (() => fileFromHash (location.hash))
  const [chatFile, setChatFile] = useState<string | null> (() => fileFromHash (location.hash))
  const [browse, setBrowse] = useState<BrowseState> (savedBrowseState)
  const [loading, setLoading] = useState (true)
  const [error, setError] = useState ('')
  const [notice, setNotice] = useState<MedicalFile | null> (null)
  const [memberDraft, setMemberDraft] = useState<MemberDraft | null> (null)
  const [managingMembers, setManagingMembers] = useState (false)
  const [memberError, setMemberError] = useState ('')
  const [memberBusy, setMemberBusy] = useState (false)
  const [uploadReviews, setUploadReviews] = useState<string[]> ([])
  const [reviewTarget, setReviewTarget] = useState<string | null> (null)
  const [editMemberFile, setEditMemberFile] = useState<string | null> (null)
  const [dirty, setDirty] = useState (false)
  const [newDirty, setNewDirty] = useState (false)
  const [chatDirty, setChatDirty] = useState (false)
  const [resetVersion, setResetVersion] = useState (0)
  const [resetting, setResetting] = useState (false)
  const [uploading, setUploading] = useState (false)
  const [resetError, setResetError] = useState ('')
  const pendingUploads = useRef (savedUploads ())
  const mutation = useRef (0)
  const resetEpoch = useRef (0)
  const refreshing = useRef (false)
  const browserScroll = useRef (0)
  const lastSelected = useRef<string | null> (selected)
  const viewer = useRef<ViewerHandle> (null)
  const importer = useRef<ImportPanelHandle> (null)

  useEffect (() => {
    sessionStorage.setItem ('appMode', demoMode ? 'demo' : 'normal')
    document.documentElement.dataset.mode = demoMode ? 'demo' : 'normal'
  }, [demoMode])

  function rememberDemo (documents: MedicalFile[])
  {
    for (const file of documents) if (file.status === 'pending' || file.status === 'processing') waitForUpload (file.id)
  }

  async function loadDemo ()
  {
    setDemoMode (true)
    setDemoBusy (true)
    setDemoError ('')
    try
    {
      const documents = await request<MedicalFile[]> ('/demo/import', {method: 'POST'})
      mutation.current++
      rememberDemo (documents)
      setFiles (old => [...documents, ...old.filter (file => !documents.some (item => item.id === file.id))])
      const members = await request<Profile[]> ('/profiles')
      setProfiles (members)
      setBrowse (old => ({...old, dimension: 'member', member: '', attention: false}))
    }
    catch (error) {setDemoError ((error as Error).message)}
    finally {setDemoBusy (false)}
  }

  useEffect (() => {
    // Root opens Records; explicit page and report links survive reloads.
    if (location.hash !== canonicalHash (location.hash)) history.replaceState (null, '', canonicalHash (location.hash))
  }, [])

  // View: src/import/ui-flow.svg#U5
  // Read files/profiles/config together. Capture the local mutation counter before
  // fetching and reject a response that predates a save/delete, avoiding stale UI resurrection.
  const refresh = useCallback (async (showLoading = false) => {
    if (refreshing.current) return
    refreshing.current = true
    if (showLoading) setLoading (true)
    const version = mutation.current
    // import/ui-flow.svg#U5: poll backend-confirmed records, profiles, and configuration.
    try
    {
      const [nextFiles, nextProfiles, nextConfig] = await Promise.all ([request<MedicalFile[]> ('/files'), request<Profile[]> ('/profiles'), request<Configuration> ('/config')])
      if (version !== mutation.current) return
      const completed = nextFiles.filter (file => pendingUploads.current.has (file.id) && (file.status === 'filed' || file.status === 'failed'))
      for (const file of completed)
      {
        pendingUploads.current.delete (file.id)
        setNotice (file)
      }
      // Consume only this tab's operations. Other clients' processing results update
      // the library and attention badges without opening dialogs or showing notices.
      pendingUploads.current = new Set ([...pendingUploads.current].filter (id => nextFiles.some (file => file.id === id)))
      sessionStorage.setItem ('pendingUploads', JSON.stringify ([...pendingUploads.current]))
      setUploadReviews (old => [...new Set ([...old, ...completed.map (file => file.id)])].filter (id => nextFiles.some (file => file.id === id && needsMemberReview (file, nextProfiles))))
      setNotice (old => old ? nextFiles.find (file => file.id === old.id) ?? null : null)
      setFiles (nextFiles)
      setProfiles (nextProfiles)
      setConfig (nextConfig)
      setError ('')
    }
    catch (error) {setError ((error as Error).message)}
    finally {setLoading (false); refreshing.current = false}
  }, [])

  useEffect (() => {
    sessionStorage.setItem ('libraryBrowse', new URLSearchParams ({view: browse.dimension, member: browse.member, attention: String (browse.attention)}).toString ())
  }, [browse])

  useEffect (() => {
    if (!selected && lastSelected.current)
    {
      const id = lastSelected.current
      requestAnimationFrame (() => {
        document.querySelector<HTMLButtonElement> (`.file-row[data-file-id="${CSS.escape (id)}"]`)?.focus ({preventScroll: true})
        window.scrollTo (0, browserScroll.current)
      })
    }
    lastSelected.current = selected
  }, [selected])

  useEffect (() => {
    const initial = window.setTimeout (() => void refresh (), 0)
    const timer = window.setInterval (() => void refresh (), 1800)
    return () => {clearTimeout (initial); clearInterval (timer)}
  }, [refresh])

  useEffect (() => {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en'
    localStorage.setItem ('language', language)
  }, [language])

  // View: src/import/ui-flow.svg#U11
  // Guard reload/hash navigation across document, new-text and chat drafts.
  // Browser events do not bypass the viewer's Save/Discard/Stay decision.
  useEffect (() => {
    function leave (event: BeforeUnloadEvent)
    {
      // import/ui-flow.svg#U11: guard unsaved drafts during reload and navigation.
      if (dirty || newDirty || chatDirty) {event.preventDefault (); event.returnValue = ''}
    }
    function hash ()
    {
      const nextRoute = canonicalHash (location.hash)
      if (location.hash !== nextRoute) history.replaceState (null, '', nextRoute)
      if (nextRoute === route) return
      const next = fileFromHash (nextRoute)
      // Tabs only hide the editor, preserving its draft. A different report
      // replaces that editor and still requires Save/Discard/Stay.
      if (next && next !== selected && dirty)
      {
        history.replaceState (null, '', route)
        viewer.current?.leave (() => {
          setDirty (false)
          setEditMemberFile (null)
          setSelected (next)
          setChatFile (next)
          setRoute (nextRoute)
          history.pushState (null, '', nextRoute)
        })
        return
      }
      if (next && next !== selected)
      {
        setDirty (false)
        setEditMemberFile (null)
        setSelected (next)
        setChatFile (next)
      }
      setRoute (nextRoute)
      if (location.hash !== nextRoute) history.replaceState (null, '', nextRoute)
    }
    window.addEventListener ('beforeunload', leave)
    window.addEventListener ('hashchange', hash)
    window.addEventListener ('popstate', hash)
    return () => {window.removeEventListener ('beforeunload', leave); window.removeEventListener ('hashchange', hash); window.removeEventListener ('popstate', hash)}
  }, [route, selected, dirty, newDirty, chatDirty])

  function navigate (next: Page)
  {
    const hash = `#${next}`
    if (hash === route) return
    history.pushState (null, '', hash)
    setRoute (hash)
  }

  // View: src/library/browsing-flow.svg#R7
  // Keep one document identity across tree, source links and viewer. Resolve dirty edits
  // before hash navigation, and remember the scroll position for a consultation-friendly return.
  function select (id: string | null)
  {
    // import/ui-flow.svg#U11: resolve one stable identity and preserve the current filters.
    const hash = id ? `#/files/${encodeURIComponent (id)}` : '#records'
    if (id && id === selected)
    {
      if (route !== hash) history.pushState (null, '', hash)
      setRoute (hash)
      viewer.current?.openSaved ()
      return
    }
    const open = () => {
      setDirty (false)
      setEditMemberFile (null)
      if (!selected && id) browserScroll.current = window.scrollY
      setSelected (id)
      if (id) setChatFile (id)
      setRoute (hash)
      if (route !== hash) history.pushState (null, '', hash)
    }
    if (viewer.current) viewer.current.leave (open)
    else open ()
  }

  // View: src/import/ui-flow.svg#U4
  // Apply the actual server receipt immediately and advance the mutation counter.
  // A later poll must not undo a confirmed local result.
  function updated (file: MedicalFile, open = true)
  {
    if (resetVersion !== resetEpoch.current) return
    mutation.current++
    // import/ui-flow.svg#U5: immediate mutations use the actual backend receipt, not a guess.
    setFiles (old => [file, ...old.filter (item => item.id !== file.id)])
    setNotice (file)
    if (file.status === 'pending' || file.status === 'processing') waitForUpload (file.id)
    if (open && selected !== file.id) select (file.id)
  }

  function waitForUpload (id: string)
  {
    pendingUploads.current.add (id)
    sessionStorage.setItem ('pendingUploads', JSON.stringify ([...pendingUploads.current]))
  }

  function stored (file: MedicalFile)
  {
    if (resetVersion !== resetEpoch.current) return
    waitForUpload (file.id)
    updated (file)
  }

  // View: src/import/ui-flow.svg#U13
  // Merge the saved member receipt, close the form, then fetch documents whose exact
  // member links may have changed on the backend.
  function profileSaved (profile: Profile)
  {
    if (resetVersion !== resetEpoch.current) return
    mutation.current++
    setProfiles (old => [...old.filter (item => item.id !== profile.id), profile])
    setMemberDraft (null)
    void refresh ()
  }

  // View: backend/library-storage.svg#S8
  // Confirm profile removal separately from report deletion. Update selection only
  // after the backend succeeds; stored reports remain available for reassignment.
  async function removeProfile (profile: Profile)
  {
    if (!await confirmation.ask ({title: t.removeMember, message: `${t.removeMemberQuestion}\n\n${profile.name}`, confirmLabel: t.removeMember, cancelLabel: t.cancel, destructive: true})) return
    setMemberError ('')
    setMemberBusy (true)
    try
    {
      await request (`/profiles/${profile.id}`, {method: 'DELETE'})
      mutation.current++
      setProfiles (old => old.filter (item => item.id !== profile.id))
      setBrowse (old => old.member === `profile:${profile.id}` ? {...old, member: ''} : old)
      await refresh ()
    }
    catch (error) {setMemberError ((error as Error).message)}
    finally {setMemberBusy (false)}
  }

  // import/ui-flow.svg#U6: library views group the same saved identities.
  const current = files.find (file => file.id === selected)
  const reviewFile = demoAcknowledged && !loading && !error && !memberDraft && !managingMembers && !dirty && !newDirty && !chatDirty && !memberBusy && !uploading && !editMemberFile ?
    files.find (file => file.id === reviewTarget && needsMemberReview (file, profiles)) ??
      files.find (file => uploadReviews.includes (file.id) && needsMemberReview (file, profiles)) : undefined

  // View: src/library/browsing-flow.svg#R5
  // Consume this tab's queued review once; later polls must not reopen it.
  function deferReview (file: MedicalFile)
  {
    setUploadReviews (old => old.filter (id => id !== file.id))
    setReviewTarget (null)
  }

  // View: src/import/ui-flow.svg#U15
  // Clear UI evidence only after the atomic server reset succeeds. Remount the
  // workspace to discard chat/import/editor state; failed resets retain that state.
  async function resetDemo ()
  {
    if (!demoMode || resetting || !await confirmation.ask ({title: t.resetDemo, message: t.resetDemoQuestion, confirmLabel: t.resetDemo, cancelLabel: t.cancel, destructive: true})) return
    setResetting (true)
    setResetError ('')
    try
    {
      const documents = await request<MedicalFile[]> ('/demo/reset', {method: 'POST', ...json ({confirm: true})})
      resetEpoch.current++
      mutation.current++
      pendingUploads.current.clear ()
      sessionStorage.removeItem ('pendingUploads')
      setFiles (documents)
      setProfiles ([])
      setSelected (null)
      setRoute ('#records')
      setChatFile (null)
      setBrowse (old => ({...old, member: '', attention: false}))
      setNotice (null)
      setMemberDraft (null)
      setManagingMembers (false)
      setMemberError ('')
      setReviewTarget (null)
      setUploadReviews ([])
      setEditMemberFile (null)
      setDirty (false)
      setNewDirty (false)
      setUploading (false)
      setChatDirty (false)
      setError ('')
      setResetVersion (resetEpoch.current)
      rememberDemo (documents)
      history.replaceState (null, '', '#records')
    }
    catch (error) {setResetError ((error as Error).message)}
    finally {setResetting (false)}
  }

  const demoDocuments = currentDemoDocuments (files)
  const demoCount = config?.demo?.file_count ?? 13
  const demoPending = demoBusy || demoDocuments.length < demoCount || demoDocuments.some (file => file.status === 'pending' || file.status === 'processing')
  const questionSources = demoDocuments.filter (file => !isLiveDemoFile (file))
  const demoChatPending = questionSources.length < (config?.demo?.prepared_count ?? 10) || questionSources.some (file => file.status !== 'filed')

  return <>
    <GlassScene key={`scene:${resetVersion}`} />
    <header className={`site-header${page === 'chat' && !showReport ? ' chat-page-header' : ''}`}><a className="brand brand-home" href="#records" aria-label={language === 'zh' ? '返回病历首页' : 'Go to Records home'} onClick={event => {event.preventDefault (); navigate ('records')}}><img className="brand-mark" src="/Logo.png" alt="" /><div><strong className="brand-product-name">{t.brand}</strong>{page === 'chat' && !showReport && <strong className="brand-chat-name">Nurse Ella</strong>}<small>{t.tagline}</small></div></a>
      <div className="header-actions"><Button unstyled role="switch" aria-label={t.demoMode} aria-checked={demoMode} aria-busy={demoBusy} className="mode-toggle" disabled={!config?.demo || demoBusy || resetting || uploading} onClick={() => {if (demoMode) setDemoMode (false); else setDemoWelcome (true)}}>
        <span className="mode-toggle-title"><span className="mode-toggle-icon"><FlaskConical aria-hidden="true" /></span>{language === 'zh' ? '演示' : 'Demo'}</span>
        <span className="mode-toggle-track" aria-hidden="true"><span className="mode-toggle-state">{demoMode ? 'ON' : 'OFF'}</span><span className="mode-toggle-thumb" /></span>
      </Button><div className="desktop-language"><Dropdown label="Language / 语言" value={language} onChange={value => setLanguage (value as 'en' | 'zh')} items={[{value: 'en', label: 'English'}, {value: 'zh', label: '简体中文'}]} /></div>
      <div className="mobile-language" role="group" aria-label="Language / 语言"><Button unstyled aria-pressed={language === 'en'} onClick={() => setLanguage ('en')}>EN</Button><Button unstyled aria-pressed={language === 'zh'} onClick={() => setLanguage ('zh')}>中文</Button></div></div>
    </header>
    <Workspace key={`workspace:${resetVersion}`} selected={showReport && Boolean (selected)} phoneChat={page === 'chat'} phoneReport={showReport} language={language} libraryStatus={resetting ? t.resettingLibrary : demoBusy ? t.loadingDemo : memberBusy ? t.removing : uploading ? t.uploading : undefined}
      libraryFooter={demoMode ? <>{resetError && <p role="alert" className="error-text">{resetError}</p>}<Button unstyled className="reset-library-button" disabled={resetting || demoBusy || uploading} onClick={() => void resetDemo ()}>{resetting ? t.resettingLibrary : t.resetDemo}</Button></> : null}
      library={<>
        {demoMode && <aside className="demo-kit-status"><strong>{t.demoMode} · {config?.demo?.title}</strong><p>{t.demoKitHelp}</p><p role="status">{demoDocuments.filter (file => file.status === 'filed').length} / {demoCount} {t.demoFiled}{demoDocuments.some (file => file.status === 'failed') && ` · ${t.demoIncomplete}`}</p>{demoError && <p role="alert">{demoError}</p>}{(demoError || demoDocuments.length < demoCount) && <Button unstyled disabled={demoBusy} onClick={() => void loadDemo ()}>{t.loadDemo}</Button>}</aside>}

        {config && !config.configured && <aside className="notice setup"><strong>{t.setup}</strong><p>{t.configure}</p></aside>}
        {notice && !demoMode && <div role="status" className="notice saved-notice"><div><strong>{notice.status === 'filed' ? t.saved : notice.status === 'failed' ? t.failed : t.originalStored}: {notice.title}</strong>
          {notice.status === 'filed' && <p>{dimensions.map (key => `${t[key]}: ${notice.metadata?.[key].values.map (value => key === 'date' ? formatDate (value.value) : value.value).join (' / ') || t.unknown}`).join (' · ')}</p>}
          {notice.check_status === 'failed' && <p>{t.checkFailed}</p>}
          {notice.concerns.length > 0 && <p>{t.concerns}: {notice.concerns.length}</p>}</div>
          <Button unstyled onClick={() => select (notice.id)}>{t.open} →</Button><Button unstyled aria-label={t.close} onClick={() => setNotice (null)}>×</Button></div>}
        <LibraryBrowser files={files} profiles={profiles} labels={t} state={browse} onChange={setBrowse} selected={selected} onSelect={select} loading={loading} error={error} onRefresh={() => void refresh (true)}
          onReviewMember={file => setReviewTarget (file.id)} onManageMembers={() => setManagingMembers (true)} onAddMember={() => setMemberDraft ({})}
          onAddRecord={config ? () => {if (demoMode) setSamplePicker (true); else importer.current?.open ()} : undefined} addingRecord={uploading} language={language} />
        {config && <div className="import-slot" hidden={demoMode}><ImportPanel ref={importer} config={config} labels={t} onStored={stored} onDirty={setNewDirty} onBusy={setUploading} /></div>}
      </>} chat={config && <ChatPanel files={files} profiles={profiles} member={browse.member} onMember={member => setBrowse (old => ({...old, member}))} viewer={files.find (file => file.id === chatFile)} onOpen={select} onClearViewer={() => setChatFile (null)} language={language} onDirty={setChatDirty} demoQuestions={demoMode ? config.demo?.questions ?? [] : undefined} demoPending={demoMode && demoChatPending} />}>
      {current ? <Viewer ref={viewer} key={`${current.id}:${editMemberFile === current.id}`} file={current} profiles={profiles} labels={t} onUpdate={file => {setEditMemberFile (null); updated (file)}} onDelete={() => {mutation.current++; setDirty (false); setEditMemberFile (null); setFiles (old => old.filter (file => file.id !== current.id)); setNotice (null); setSelected (null); navigate ('records')}} onBack={() => select (null)} onDirty={setDirty} resolveMember={editMemberFile === current.id} onResolveDone={() => setEditMemberFile (null)} onReviewMember={() => setReviewTarget (current.id)} /> : selected ? <div className="viewer-placeholder">{loading ? <Loading center label={t.loading} /> : error ? t.failedLoad : t.unavailableFile}<Button unstyled onClick={() => select (null)}>{t.back}</Button></div> : demoMode ? <section className="demo-overview"><small>{t.demoMode} · {config?.demo?.title}</small><h2>{t.demoTitle}</h2><p>{t.demoOverview}</p>{demoPending && <Loading center label={t.demoProcessing} />}<Button unstyled className="primary" disabled={!demoDocuments.length} onClick={() => select (demoDocuments[0].id)}>{t.demoOpen}</Button></section> : null}
    </Workspace>
    <nav className="phone-navigation" aria-label={language === 'zh' ? '工作区' : 'Workspace'}>
      <Button unstyled aria-pressed={page === 'records'} onClick={() => navigate ('records')}>{language === 'zh' ? '病历' : 'Records'}</Button>
      <Button unstyled aria-pressed={page === 'chat'} onClick={() => navigate ('chat')}>Chat</Button>
    </nav>
    {managingMembers && <MemberManager profiles={profiles} files={files} labels={t} language={language} busy={memberBusy} error={memberError}
      onAdd={() => setMemberDraft ({})} onEdit={profile => setMemberDraft ({profile})} onRemove={profile => {if (!memberBusy) void removeProfile (profile)}} onClose={() => setManagingMembers (false)} />}
    {demoWelcome && config && <DemoWelcome config={config} language={language} onClose={() => setDemoWelcome (false)} onStart={() => {setDemoWelcome (false); void loadDemo ()}} />}
    {samplePicker && <DemoSamplePicker language={language} onStored={stored} onBusy={setUploading} onClose={() => setSamplePicker (false)} />}
    {memberDraft && <MemberForm draft={memberDraft} labels={t} onSaved={profileSaved} onClose={() => setMemberDraft (null)} />}
    {reviewFile && <MemberReview key={memberReviewKey (reviewFile)} file={reviewFile} labels={t} onLater={() => deferReview (reviewFile)}
      onMistake={() => {deferReview (reviewFile); select (reviewFile.id); setEditMemberFile (reviewFile.id)}}
      onNew={() => {deferReview (reviewFile); setMemberDraft ({detectedName: reviewFile.metadata!.member.values[0].value})}} />}
    <footer className="demo-footer"><span className="desktop-footer-copy">{t.demoFooter}</span><div className="mobile-footer-copy"><span>{language === 'zh' ? '仅供病历查询，不替代医生建议' : 'For record queries · Not a substitute for medical advice'}</span><details><summary>{language === 'zh' ? '使用说明' : 'About'}</summary><div>{t.demoFooter}<p>{language === 'zh' ? '上传的文档与问题会发送给配置的 AI 服务进行处理。' : 'Uploaded documents and questions are sent to the configured AI service for processing.'}</p></div></details></div></footer>
    {confirmation.dialog}
    {!demoAcknowledged && <DemoNotice language={language} onContinue={() => setDemoAcknowledged (true)} />}
  </>
}

export default App
