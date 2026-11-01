import {Button} from '@chakra-ui/react'
import {useEffect, useRef, useState} from 'react'
import './demo-notice.css'

const copy = {
  en: {
    title: 'Demo only — please do not upload real medical records',
    intro: 'This is a hackathon demo of Family Medical Records, a family medical-records assistant. The sample records provided for this demo are synthetic and do not belong to any real person.',
    uploads: 'Please do not upload real medical documents, ID cards, or any personal information. Use the supplied sample files, or create your own fictional ones. Please do not abuse or spam the demo.',
    handling: 'How your data is handled',
    processing: "Uploaded files and questions are sent to Google's Gemini API (paid tier) for text extraction and answering. Under Google's paid-service terms, this content is not used to train or improve its models, but logs may be kept for a limited period to detect abuse.",
    storage: 'Uploaded files are stored on our server until they are deleted or the shared library is reset. Do not assume anything you upload is private.',
    cookies: 'The app does not use cookies for tracking or analytics. Browser storage remembers your language, layout, and browsing preferences.',
    boundaryTitle: 'Not medical advice',
    boundary: 'AI answers can be wrong. This tool organizes and searches records; it does not diagnose or recommend treatment.',
    acknowledgement: 'I understand this is a demo and I will not upload real medical information.',
    continue: 'Continue',
  },
  zh: {
    title: '仅供演示 — 请勿上传真实医疗记录',
    intro: '这是家庭医疗档案助手 Family Medical Records 的黑客松演示。演示提供的样本记录均为虚构，不属于任何真实个人。',
    uploads: '请勿上传真实医疗文件、身份证件或任何个人信息。请使用提供的样本文件，或自行创建虚构资料。请勿滥用演示或频繁发送垃圾请求。',
    handling: '您的数据如何处理',
    processing: '上传的文件和问题会发送至 Google 的 Gemini API（付费层级），用于文字提取和回答。根据 Google 的付费服务条款，这些内容不会用于训练或改进其模型，但可能保留有限时间的日志以检测滥用。',
    storage: '上传的文件会存储在我们的服务器上，直到文件被删除或共享档案库被重置。请不要认为上传的任何内容是私密的。',
    cookies: '本应用不使用 Cookie 进行追踪或分析。浏览器存储会记住您的语言、布局和浏览偏好。',
    boundaryTitle: '不构成医疗建议',
    boundary: 'AI 回答可能出错。本工具用于整理和搜索记录，不进行诊断，也不推荐治疗。',
    acknowledgement: '我理解这是演示，不会上传真实医疗信息。',
    continue: '继续',
  },
}

// View: src/import/ui-flow.svg#U16
// A native modal blocks interaction and traps focus until the demo-only notice is
// acknowledged. Acceptance lasts only for this page load; Escape cannot bypass it.
// The content scrolls independently while acknowledgement and Continue stay visible.
export function DemoNotice ({language, onContinue}: {language: 'en' | 'zh'; onContinue: () => void})
{
  const dialog = useRef<HTMLDialogElement> (null)
  const [acknowledged, setAcknowledged] = useState (false)
  const t = copy[language]

  useEffect (() => {dialog.current?.showModal ()}, [])

  return <dialog ref={dialog} className="demo-notice" aria-labelledby="demo-notice-title" aria-describedby="demo-notice-intro" onCancel={event => event.preventDefault ()}>
    <header className="demo-notice-header"><h2 id="demo-notice-title">{t.title}</h2></header>
    <div className="demo-notice-content" tabIndex={0}>
      <p id="demo-notice-intro">{t.intro}</p>
      <p>{t.uploads}</p>
      <h3>{t.handling}</h3>
      <ul><li>{t.processing}</li><li>{t.storage}</li><li>{t.cookies}</li></ul>
      <h3>{t.boundaryTitle}</h3><p>{t.boundary}</p>
    </div>
    <form className="demo-notice-controls" onSubmit={event => {
      event.preventDefault ()
      if (!acknowledged) return
      dialog.current?.close ()
      onContinue ()
    }}>
      <label className="demo-acknowledgement"><input type="checkbox" required checked={acknowledged} onChange={event => setAcknowledged (event.target.checked)} /><span>{t.acknowledgement}</span></label>
      <Button unstyled type="submit" className="primary demo-continue" disabled={!acknowledged}>{t.continue}</Button>
    </form>
  </dialog>
}
