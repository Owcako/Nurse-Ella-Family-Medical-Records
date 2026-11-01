import {useRef, useState} from 'react'
import type {CSSProperties, ReactNode} from 'react'
import {Button} from '@chakra-ui/react'
import {Loading} from './Loading'

type PanelState = {library: number; chat: number; libraryClosed: boolean; chatClosed: boolean}

// View: src/import/ui-flow.svg#U14
// Treat browser-stored layout as untrusted preferences: parse defensively and clamp
// widths so malformed storage cannot leave the records or chat unusable.
function savedLayout (): PanelState
{
  try
  {
    const saved = JSON.parse (localStorage.getItem ('workspaceLayout') ?? '{}')
    return {
      library: Number.isFinite (saved.library) ? Math.max (240, Math.min (520, saved.library)) : 300,
      chat: Number.isFinite (saved.chat) ? Math.max (240, Math.min (520, saved.chat)) : 340,
      libraryClosed: saved.libraryClosed === true, chatClosed: saved.chatClosed === true,
    }
  }
  catch {return {library: 300, chat: 340, libraryClosed: false, chatClosed: false}}
}

// View: src/import/ui-flow.svg#U14
// Compose three presentation regions without owning medical data. Persist only
// panel dimensions/collapse choices; phone navigation selects a suitable view.
export function Workspace ({children, library, libraryFooter, libraryStatus, chat, selected, phoneChat, phoneReport, language}: {
  children: ReactNode; library: ReactNode; libraryFooter?: ReactNode; libraryStatus?: string; chat: ReactNode; selected: boolean; phoneChat: boolean; phoneReport: boolean; language: 'en' | 'zh'
})
{
  const [layout, setLayout] = useState (savedLayout)
  const drag = useRef<{side: 'library' | 'chat'; x: number; width: number; next: number; restore: number} | null> (null)
  const root = useRef<HTMLElement> (null)
  const names = language === 'zh' ? {library: '病历', chat: 'Chat', expand: '展开', collapse: '收起', resize: '调整宽度'} :
    {library: 'Records', chat: 'Chat', expand: 'Expand', collapse: 'Collapse', resize: 'Resize'}

  // View: src/import/ui-flow.svg#U14
  // Persist a completed layout action so a reload restores the user's workspace.
  function update (next: PanelState)
  {
    setLayout (next)
    localStorage.setItem ('workspaceLayout', JSON.stringify (next))
  }

  // View: src/import/ui-flow.svg#U14
  // Support pointer capture, keyboard resizing and bounded widths. Commit on release;
  // restore a safe width on pointer cancellation so a half-finished gesture does not corrupt layout.
  function separator (side: 'library' | 'chat')
  {
    const closed = side === 'library' ? 'libraryClosed' : 'chatClosed'
    return <div className={`resize-handle resize-${side}`} role="separator" aria-label={`${names.resize} ${names[side]}`} aria-orientation="vertical"
      aria-valuemin={0} aria-valuemax={520} aria-valuenow={layout[closed] ? 0 : layout[side]} tabIndex={0}
      onDoubleClick={() => update ({...layout, [closed]: !layout[closed]})}
      onKeyDown={event => {
        if (event.key === 'Enter') {event.preventDefault (); update ({...layout, [closed]: !layout[closed]}); return}
        if (event.key === 'Home') {event.preventDefault (); update ({...layout, [closed]: true}); return}
        if (event.key === 'End') {event.preventDefault (); update ({...layout, [side]: 520, [closed]: false}); return}
        if (!['ArrowLeft', 'ArrowRight'].includes (event.key)) return
        event.preventDefault ()
        const width = layout[side] + (event.key === 'ArrowRight' ? 20 : -20) * (side === 'library' ? 1 : -1)
        update ({...layout, [side]: width < 240 ? layout[side] : Math.min (520, width), [closed]: width < 240})
      }}
      onPointerDown={event => {
        if (event.button !== 0) return
        event.preventDefault ()
        event.currentTarget.setPointerCapture (event.pointerId)
        const width = root.current?.querySelector (`.${side === 'library' ? 'library-pane' : 'chat-shell'}`)?.getBoundingClientRect ().width ?? layout[side]
        drag.current = {side, x: event.clientX, width, next: width, restore: layout[side]}
      }}
      onPointerMove={event => {
        if (!drag.current || drag.current.side !== side) return
        const other = side === 'library' ? (layout.chatClosed ? 44 : layout.chat) : (layout.libraryClosed ? 44 : layout.library)
        const limit = Math.max (240, Math.min (520, (root.current?.clientWidth ?? window.innerWidth) - other - 320))
        const next = Math.max (44, Math.min (limit, drag.current.width + (event.clientX - drag.current.x) * (side === 'library' ? 1 : -1)))
        drag.current.next = next
        setLayout (old => ({...old, [side]: next, [closed]: false}))
      }}
      onPointerUp={event => {
        if (!drag.current) return
        const next = drag.current.next
        const restore = drag.current.restore
        drag.current = null
        update ({...layout, [side]: next < 240 ? restore : next, [closed]: next < 240})
        event.currentTarget.releasePointerCapture (event.pointerId)
      }} onPointerCancel={() => {
        const restore = drag.current?.restore ?? Math.max (240, layout[side])
        drag.current = null
        update ({...layout, [side]: restore})
      }}><span /></div>
  }

  // View: src/import/ui-flow.svg#U14
  // Expose collapse state through aria-expanded and retain the last usable panel width.
  function toggle (side: 'library' | 'chat')
  {
    const closed = side === 'library' ? 'libraryClosed' : 'chatClosed'
    return <Button unstyled className="panel-toggle" aria-label={`${layout[closed] ? names.expand : names.collapse} ${names[side]}`}
      aria-expanded={!layout[closed]} onClick={() => update ({...layout, [closed]: !layout[closed]})}>
      {side === 'library' ? layout[closed] ? '›' : '‹' : layout[closed] ? '‹' : '›'}
    </Button>
  }

  return <main ref={root} className={`workspace${selected ? ' has-selection' : ''}${phoneChat ? ' phone-chat' : ''}${phoneReport ? ' phone-report' : ''}`}
    data-library-closed={layout.libraryClosed} data-chat-closed={layout.chatClosed}
    style={{'--library-width': `${layout.libraryClosed ? 44 : layout.library}px`, '--chat-width': `${layout.chatClosed ? 44 : layout.chat}px`} as CSSProperties}>
    <section className="library-pane floating-panel" aria-busy={Boolean (libraryStatus)}><div className="panel-bar"><span>{names.library}</span>{toggle ('library')}</div><div className="panel-content" inert={Boolean (libraryStatus)}>{library}</div>{libraryFooter && <div className="library-footer" inert={Boolean (libraryStatus)}>{libraryFooter}</div>}{libraryStatus && <Loading overlay label={libraryStatus} />}</section>
    {separator ('library')}
    <aside className="viewer-pane">{children}</aside>
    {separator ('chat')}
    <aside className="chat-shell floating-panel"><div className="panel-bar"><span><span className="chat-panel-desktop-title">{names.chat}</span><span className="chat-panel-phone-title">{language === 'zh' ? '对话家庭成员' : 'Chat member'}</span></span>{toggle ('chat')}</div><div className="panel-content">{chat}</div></aside>
  </main>
}
