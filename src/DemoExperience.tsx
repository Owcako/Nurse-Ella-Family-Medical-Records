import {Button} from '@chakra-ui/react'
import {useEffect, useRef, useState} from 'react'
import type {Configuration, MedicalFile} from './import/types'
import {operationKey, request} from './import/api'
import {Loading} from './Loading'
import './demo-experience.css'

export function DemoWelcome ({config, language, onStart, onClose}: {
  config: Configuration; language: 'en' | 'zh'; onStart: () => void; onClose: () => void
})
{
  const dialog = useRef<HTMLDialogElement> (null)
  const zh = language === 'zh'
  useEffect (() => {
    const element = dialog.current!
    element.showModal ()
    element.querySelector<HTMLHeadingElement> ('h2')?.focus ({preventScroll: true})
    return () => element.close ()
  }, [])
  return <dialog ref={dialog} className="modal profile-dialog demo-experience" aria-labelledby="demo-welcome-title" onCancel={event => {event.preventDefault (); onClose ()}}>
    <h2 id="demo-welcome-title" tabIndex={-1}>{zh ? '欢迎体验 Demo' : 'Welcome to the demo'}</h2>
    <p>{zh ? `已为你准备 ${config.demo?.profile_count ?? 2} 位家庭成员、${config.demo?.file_count ?? 13} 份虚构病历档案，方便快速体验。` : `Explore ${config.demo?.file_count ?? 13} fictional records for ${config.demo?.profile_count ?? 2} family members.`}</p>
    <ul>
      <li><strong>{zh ? '浏览病历' : 'Browse records'}</strong><p>{zh ? '预处理档案已通过 AI 整理并保存，可立即查看原始报告和提取内容；其余档案现场处理。' : 'Preprocessed records have saved AI results, with original reports and extracted text ready to view. The remaining records are processed live.'}</p></li>
      <li><strong>{zh ? '试试导入' : 'Try importing'}</strong><p>{zh ? '「添加病历」提供 2 份 PDF 和 1 张图片供选择。新增文件会经过真实的 AI 识别、整理和归档。' : 'Add record offers 2 PDF samples and 1 photo. New imports go through live AI extraction, organization and filing.'}</p></li>
      <li><strong>{zh ? '体验问答' : 'Ask questions'}</strong><p>{zh ? 'Chat 提供示例问题。每次回答均由 AI 实时检索病历并生成，并非预存答案。' : 'Choose a sample question in Chat. Every answer is generated live by AI searching the records, not a stored answer.'}</p></li>
    </ul>
    <p className="demo-experience-note">{zh ? '所有样例均为虚构数据，请勿上传真实个人医疗资料。' : 'All samples are fictional. Do not upload real personal medical records.'}</p>
    <div className="actions"><Button unstyled onClick={onClose}>{zh ? '取消' : 'Cancel'}</Button><Button unstyled className="primary" onClick={onStart}>{zh ? '开始体验' : 'Start exploring'}</Button></div>
  </dialog>
}

type Sample = {id: string; filename: string; media: string; available: boolean}

export function DemoSamplePicker ({language, onStored, onBusy, onClose}: {
  language: 'en' | 'zh'; onStored: (file: MedicalFile) => void; onBusy: (busy: boolean) => void; onClose: () => void
})
{
  const dialog = useRef<HTMLDialogElement> (null)
  const keys = useRef<Record<string, string>> ({})
  const [samples, setSamples] = useState<Sample[]> ([])
  const [loading, setLoading] = useState (true)
  const [busy, setBusy] = useState ('')
  const [error, setError] = useState ('')
  const zh = language === 'zh'
  useEffect (() => {
    const element = dialog.current!
    element.showModal ()
    return () => element.close ()
  }, [])
  useEffect (() => {
    let active = true
    request<Sample[]> ('/demo/samples').then (items => {if (active) setSamples (items)}).catch (error => {if (active) setError ((error as Error).message)}).finally (() => {if (active) setLoading (false)})
    return () => {active = false}
  }, [])

  async function importSample (sample: Sample)
  {
    setBusy (sample.id)
    onBusy (true)
    setError ('')
    keys.current[sample.id] ??= operationKey ()
    try
    {
      const file = await request<MedicalFile> (`/demo/samples/${sample.id}/import`, {method: 'POST', headers: {'Idempotency-Key': keys.current[sample.id]}})
      onStored (file)
      onClose ()
    }
    catch (error) {setError ((error as Error).message)}
    finally {setBusy (''); onBusy (false)}
  }

  return <dialog ref={dialog} className="modal profile-dialog demo-experience" aria-labelledby="demo-samples-title" onCancel={event => {event.preventDefault (); if (!busy) onClose ()}}>
    <h2 id="demo-samples-title">{zh ? '选择测试病历' : 'Choose a sample record'}</h2>
    <p>{zh ? '选择下面的样例直接导入，体验真实的 AI 识别和归档流程。' : 'Choose a sample to import and try live AI extraction and filing.'}</p>
    {loading && <Loading center label={zh ? '正在加载样例…' : 'Loading samples…'} />}
    <div className="demo-sample-cards">{samples.map ((sample, index) => <Button unstyled key={sample.id} disabled={!sample.available || Boolean (busy)} onClick={() => void importSample (sample)}>
      <span className="demo-sample-icon" aria-hidden="true">{sample.media === 'application/pdf' ? 'PDF' : 'JPG'}</span>
      <span><strong>{sample.media === 'application/pdf' ? `${zh ? '测试 PDF' : 'Sample PDF'} ${index + 1}` : zh ? '测试图片' : 'Sample image'}</strong><small>{!sample.available ? zh ? '素材准备中' : 'Not yet available' : busy === sample.id ? zh ? '正在导入…' : 'Importing…' : sample.filename}</small></span>
      <span>{sample.available ? zh ? '导入 →' : 'Import →' : ''}</span>
    </Button>)}</div>
    {error && <p className="notice error" role="alert">{error}</p>}
    <div className="actions"><Button unstyled disabled={Boolean (busy)} onClick={onClose}>{zh ? '关闭' : 'Close'}</Button></div>
  </dialog>
}
