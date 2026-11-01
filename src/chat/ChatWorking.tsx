import {useEffect, useState} from 'react'
import type {ChatProgress} from './progress'

const labels = {
  en: {preparing: 'Connecting to your record library', searching: 'Finding relevant records', reading: 'Reading the selected reports', reading_original: 'Checking the original report', answering: 'Organizing an answer from the records', reviewing: 'Checking the answer against its sources'},
  zh: {preparing: '正在连接档案库', searching: '正在查找相关档案', reading: '正在阅读选中的报告', reading_original: '正在核对报告原件', answering: '正在根据报告整理答案', reviewing: '正在核对答案和原文来源'},
}

export function ChatWorking ({language, progress}: {language: 'en' | 'zh'; progress: ChatProgress})
{
  const [started] = useState (() => performance.now ())
  const [seconds, setSeconds] = useState (0)
  useEffect (() => {
    const timer = window.setInterval (() => setSeconds (Math.floor ((performance.now () - started) / 1000)), 1000)
    return () => clearInterval (timer)
  }, [started])
  const label = labels[language][progress.stage] ?? labels[language].preparing
  return <div className="chat-working-card">
      <div className="chat-working-header"><strong>{language === 'zh' ? '正在思考…' : 'Thinking…'}</strong>
      <div className="chat-working-time" role="timer">{language === 'zh' ? `已工作 ${seconds} 秒` : `Working for ${seconds}s`}</div>
      </div>
      <div className="chat-working-stage" role="status" aria-live="polite" aria-atomic="true"><span>{label}{progress.stage === 'reading' && progress.count ? language === 'zh' ? `（${progress.count} 份）` : ` (${progress.count})` : ''}</span><span className="chat-working-dots" aria-hidden="true"><i /><i /><i /></span></div>
      <p>{language === 'zh' ? '完成核对后会显示答案，请稍候。' : 'Your answer will appear after the source check.'}</p>
  </div>
}
