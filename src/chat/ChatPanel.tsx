import {Button, Textarea} from '@chakra-ui/react'
import {Dropdown} from '../Dropdown'
import {useEffect, useRef, useState} from 'react'
import Markdown from 'react-markdown'
import {json} from '../import/api'
import type {DemoQuestion, MedicalFile, Profile} from '../import/types'
import {memberIdentity} from '../library/browsing'
import './chat.css'
import {ChatWorking} from './ChatWorking'
import {requestChat} from './progress'
import type {ChatProgress} from './progress'
import {demoMember} from '../demo'

type Reply = {
  message?: string
  service?: string
  claims: {text: string; citations: {file_id: string; quote: string}[]}[]
  explanation: string; limitation: string
  references?: string[]
  sources: {file_id: string; title: string; revision: number; kind?: string; status?: string; missing_fields?: string[]; text_origin: string; check_status: string; concerns: {quote: string; reason: string}[]}[]
  search: {total: number; indexed: number; retrieved: number}
}
type Message = {id: number; question: string; reply?: Reply; error?: string; member: string; member_name: string; viewer_id: string | null}
const copy = {
  en: {
    viewer: 'Currently selected record', clearViewer: 'Clear selected record', scopeHelp: 'Other relevant records for the selected members will still be searched.', outsideScope: 'This document is outside the chat member filter. Choose its member or All family members to include it.',
    title: 'Nurse Ella', intro: 'We can talk through your health history, questions, or next visit.', member: 'Chat member', all: 'All family members',
    placeholder: 'What’s on your mind?', question: 'Message', send: 'Send',
    thinking: 'Thinking…', failed: 'Could not complete this message. Your draft is kept.',
    demoQuestion: 'Choose a question about John Smith', choose: 'Choose a question…', demoWait: 'Some demo records are processing or unavailable. You can ask now; answers use available saved records and may be incomplete.',
    prepared: 'Prepared demo extraction',
    sources: 'Sources', evidence: 'Open saved text', review: 'Take a look',
    scope: 'Member', search: 'Search coverage', indexed: 'indexed', read: 'read', of: 'of',
    caution: 'Sources have text warnings, stale checks, or manual edits. Review the supporting report.', boundary: 'Answers explain saved records. Medication and treatment decisions belong with your clinician.',
    sourceChanged: 'This source changed or is unavailable. Ask again to refresh the answer.', edited: 'Manually edited text', extracted: 'Extracted text', userText: 'User-entered text', originalRead: 'Original transcription', unresolved: 'Unresolved fields',
  },
  zh: {
    viewer: '当前选中病历', clearViewer: '取消选中病历', scopeHelp: '仍会检索所选成员的其他相关病历。', outsideScope: '此文档不在对话成员筛选范围内。请选择其所属成员或所有家庭成员以包含该文档。',
    title: 'Nurse Ella', intro: '可以聊聊您的健康经历、疑问，或下一次就诊。', member: '对话家庭成员', all: '所有家庭成员',
    placeholder: '您想聊些什么？', question: '消息', send: '发送', thinking: '正在思考…', failed: '消息未完成，草稿已保留。',
    demoQuestion: '选择关于 John Smith 的问题', choose: '请选择问题…', demoWait: '部分演示档案仍在处理或不可用。现在即可提问；回答仅依据可用的已保存记录，可能不完整。',
    prepared: '演示预处理文本',
    sources: '来源', evidence: '打开已保存文本', review: '一起看看', scope: '成员', search: '检索范围', indexed: '已查看索引', read: '已读取', of: '/',
    caution: '来源含文本疑点、过期检查或人工修改，请核对原报告。', boundary: '回答用于理解已保存记录。用药和治疗决定请咨询医生。',
    sourceChanged: '来源已更改或不可用。请重新提问以更新回答。', edited: '人工修改文本', extracted: '提取文本', userText: '用户输入文本', originalRead: '原件转录', unresolved: '未解决分类',
  },
}

// View: backend/chat-flow.svg#C9
// Allow a small Markdown subset for readable answers. Unsupported elements are
// unwrapped rather than injecting arbitrary model-generated HTML into the page.
function AnswerText ({children}: {children: string})
{
  return <Markdown allowedElements={['p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'code']} unwrapDisallowed>{children}</Markdown>
}

// View: AGENTS.svg#F5
// Keep conversations separate by the shared member selection and in browser memory.
// The viewer is optional context; source links reopen stable saved document identities.
export function ChatPanel ({files, profiles, member: selectedMember, onMember, viewer, onOpen, onClearViewer, language, onDirty, demoQuestions, demoPending}: {
  files: MedicalFile[]; profiles: Profile[]; member: string; onMember: (member: string) => void
  viewer?: MedicalFile; onOpen: (id: string) => void; onClearViewer: () => void
  language: 'en' | 'zh'; onDirty: (dirty: boolean) => void
  demoQuestions?: DemoQuestion[]; demoPending?: boolean
})
{
  const t = copy[language]
  const [message, setMessage] = useState ('')
  const input = useRef<HTMLTextAreaElement> (null)
  useEffect (() => {
    if (input.current && window.matchMedia ('(max-width: 700px)').matches)
    {
      input.current.style.height = '0px'
      input.current.style.height = `${Math.min (80, Math.max (40, input.current.scrollHeight))}px`
    }
  }, [message])
  const [demoQuestion, setDemoQuestion] = useState ('')
  const [messages, setMessages] = useState<Message[]> ([])
  const [busy, setBusy] = useState (false)
  const [progress, setProgress] = useState<ChatProgress> ({stage: 'preparing'})
  const nextMessage = useRef (0)
  const end = useRef<HTMLDivElement> (null)
  const john = demoMember (profiles)
  const member = demoQuestions ? john ? `profile:${john.id}` : '' : selectedMember
  const questionText = demoQuestions ? demoQuestions.find (item => item.id === demoQuestion)?.question ?? '' : message
  const conversation = messages.filter (item => item.member === member)
  const scope = profiles.find (profile => `profile:${profile.id}` === member)?.name ?? t.all

  useEffect (() => {
    const frame = requestAnimationFrame (() => end.current?.scrollIntoView ({block: 'nearest', behavior: 'smooth'}))
    return () => cancelAnimationFrame (frame)
  }, [messages, member])

  // View: backend/chat-flow.svg#C1
  // Send the full current member conversation and viewer ID. Do not send unsaved
  // editor text or silently truncate history; failed requests retain the message draft.
  async function send ()
  {
    if (busy || !questionText.trim () || (demoQuestions && !john)) return
    const id = ++nextMessage.current
    const question = questionText.trim ()
    const draft = message
    setProgress ({stage: 'preparing'})
    setBusy (true)
    setMessages (old => [...old, {id, question, member, member_name: scope, viewer_id: viewer?.id ?? null}])
    if (!demoQuestions) {setMessage (''); onDirty (false)}
    try
    {
      // Preserve every exchange and its source references. The backend supplies
      // the complete current catalog and re-reads saved evidence on demand.
      const history = conversation.flatMap (item => item.reply ? [
        {role: 'user', content: item.question},
        {role: 'assistant', content: JSON.stringify ({answer: item.reply, viewer_id: item.viewer_id})},
      ] : [])
      const options = json ({message: question, history, member, viewer_id: viewer?.id ?? null, language})
      const reply = await requestChat<Reply> ({...options, method: 'POST'}, setProgress)
      setMessages (old => old.map (item => item.id === id ? {...item, reply} : item))
    }
    catch (error)
    {
      setMessages (old => old.map (item => item.id === id ? {...item, error: (error as Error).message} : item))
      if (!demoQuestions) {setMessage (draft); onDirty (Boolean (draft))}
    }
    finally {setBusy (false)}
  }

  // View: AGENTS.svg#F6
  // Render answer limitations and source status alongside links back to saved evidence.
  // A changed/deleted source is visibly stale rather than silently supporting an old answer.
  return <section className="chat-pane" aria-label={t.title}>
    <div className="chat-heading"><div><div className="eyebrow">{language === 'zh' ? '对话' : 'Conversation'}</div><h2>{t.title}</h2></div></div>
    <div className="chat-context"><Dropdown label={t.member} showLabel value={member} disabled={busy || Boolean (demoQuestions)} onChange={onMember} items={[{value: '', label: t.all}, ...profiles.map (profile => ({value: `profile:${profile.id}`, label: profile.name}))]} /></div>
    {viewer && <aside className="notice viewer-chat-context" aria-label={t.viewer}>
      <div className="selected-record-row"><div><span>{t.viewer}: </span><a href={`#/files/${encodeURIComponent (viewer.id)}`} onClick={event => {event.preventDefault (); onOpen (viewer.id)}}>{viewer.title}</a></div>
        <Button unstyled className="clear-selected-record" aria-label={t.clearViewer} title={t.clearViewer} disabled={busy} onClick={onClearViewer}>×</Button>
      </div>
      <p>{member && memberIdentity (viewer, profiles) !== member ? t.outsideScope : t.scopeHelp}</p>
    </aside>}
    <div className="chat-messages" role="log" aria-live="polite">
      {conversation.map (item => {
        const reply = item.reply
        return <article className="chat-turn" key={item.id}>
        <div className="chat-question"><small>{t.scope}: {item.member ? item.member_name : t.all}</small><p>{item.question}</p></div>
        <div className="chat-answer" data-state={reply ? 'complete' : item.error ? 'failed' : 'thinking'}>
          {reply ? <>
          {reply.message ? <div className="chat-message"><AnswerText>{reply.message}</AnswerText></div> : reply.claims.map ((claim, i) => <div className="chat-claim" key={i}><AnswerText>{claim.text}</AnswerText></div>)}
          {reply.explanation && <div className="chat-general"><AnswerText>{reply.explanation}</AnswerText></div>}
          {reply.limitation && <div className="chat-limitation"><AnswerText>{reply.limitation}</AnswerText></div>}
          {!!reply.references?.length && <div className="chat-references evidence-links">{reply.sources.filter (source => reply.references?.includes (source.file_id)).map (source => <a key={source.file_id} href={`#/files/${encodeURIComponent (source.file_id)}`} onClick={event => {event.preventDefault (); onOpen (source.file_id)}}>{t.review}: {source.title} ↗</a>)}</div>}
          {reply.sources.some (source => files.find (file => file.id === source.file_id)?.revision !== source.revision) && <p className="notice">{t.sourceChanged}</p>}
          <details className="chat-evidence"><summary><span className="desktop-source-label">{t.sources}</span><span className="mobile-source-label">{language === 'zh' ? '来源与检索详情' : 'Sources & search details'}</span></summary>
            {reply.sources.some (source => source.check_status !== 'checked' || source.concerns.length || source.text_origin === 'user_edited') && <p className="notice">{t.caution}</p>}
            {reply.sources.map (source => <div className="chat-source-status" key={source.file_id}>
              <div className="evidence-links"><a href={`#/files/${encodeURIComponent (source.file_id)}`} onClick={event => {event.preventDefault (); onOpen (source.file_id)}}>{t.evidence}: {source.title} ↗</a></div>
              <small>{source.text_origin === 'demo_prepared' ? t.prepared : source.kind === 'original_transcription' ? t.originalRead : source.text_origin === 'user_edited' ? t.edited : source.text_origin === 'user_entered' ? t.userText : t.extracted}</small>
              {[...new Set (reply.claims.flatMap (claim => claim.citations.filter (citation => citation.file_id === source.file_id).map (citation => citation.quote)))].map (quote => <blockquote key={quote}>{quote}</blockquote>)}
              {!!source.missing_fields?.length && <p>{t.unresolved}: {source.missing_fields.join (' / ')}</p>}
              {source.concerns.map ((concern, i) => <blockquote key={i}>{concern.quote}<p>{concern.reason}</p></blockquote>)}
            </div>)}
            <small className="search-coverage">{t.search}: {reply.search.indexed} {t.indexed}, {reply.search.retrieved} {t.read} {t.of} {reply.search.total}</small>
            {reply.service && <small className="chat-service">{reply.service}</small>}
          </details>
          </> : item.error ? <p role="alert" className="chat-reply-error">{t.failed} {item.error}</p> : <ChatWorking language={language} progress={progress} />}
        </div>
      </article>})}
      <div ref={end} />
    </div>
    <form className="chat-composer" onSubmit={event => {event.preventDefault (); void send ()}}>
      {demoQuestions ? <Dropdown className="demo-question-picker" menuClassName="demo-question-menu" label={t.demoQuestion} showLabel value={demoQuestion} disabled={busy}
        items={[{value: '', label: t.choose}, ...demoQuestions.map (item => ({value: item.id, label: `${item.id} · ${item.question}`}))]}
        onChange={setDemoQuestion} /> : <label><span className="composer-label">{t.question}</span><Textarea ref={input} aria-label={t.question} unstyled rows={2} maxLength={6000} value={message} disabled={busy} placeholder={t.placeholder} onChange={event => {setMessage (event.target.value); onDirty (Boolean (event.target.value))}}
        onKeyDown={event => {if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !window.matchMedia ('(max-width: 700px)').matches) {event.preventDefault (); void send ()}}} /></label>}
      <Button unstyled type="submit" className="primary chat-send" disabled={busy || !questionText.trim () || Boolean (demoQuestions && !john)}>{t.send}</Button>
      <small className={demoQuestions ? 'demo-question-help' : 'keyboard-hint'}>{demoQuestions ? demoPending ? t.demoWait : questionText : language === 'zh' ? 'Enter 发送 · Shift + Enter 换行' : 'Enter to send · Shift + Enter for a new line'}</small>
      <p className="chat-help">{t.boundary}</p>
    </form>
  </section>
}
