// View: implementation-architecture.svg#O7
// Browser response shapes mirror stored document revisions, independent stage states,
// source provenance and archive status. These types describe receipts; they do not validate HTTP input.
// Architecture: ../../implementation-architecture.svg#O7; mirrors backend response shapes.
export type Evidence = { value: string; quote: string; profile_id?: string; department_code?: string | null; source?: 'initial_text' }
export type Dimension = 'member' | 'date' | 'department' | 'disease'
export type Classification = {
  status: 'known' | 'missing' | 'ambiguous'
  values: Evidence[]
  candidates: Evidence[]
  provenance: 'documented' | 'user_supplied' | 'ai_classified'
}
export type MedicalFile = {
  id: string
  record_id: string
  original_filename: string | null
  archive: {
    title: string
    patient_name: string | null
    patient_status: string
    date_label: string | null
    department_code: string
    document_count: number
    index_state: string
    index_error: string | null
  }
  title: string
  media: string
  origin: string
  revision: number
  status: 'pending' | 'processing' | 'failed' | 'filed'
  stage: string
  error: string | null
  extraction_status: string
  extraction_error: string | null
  initial_text: string | null
  text: string | null
  text_origin: string
  check_status: string
  text_revision?: number
  checked_text_revision?: number | null
  check_error?: string
  concerns: { quote: string; reason: string; start: number; end: number; reviewed?: boolean }[]
  metadata: Record<Dimension, Classification> | null
}
export type Profile = { id: string; name: string; aliases: string[] }
export type Configuration = {
  demo?: {title: string; file_count: number; profile_count?: number; questions: DemoQuestion[]; prepared_count?: number; live_count?: number}
  service: string
  configured: boolean
  max_bytes: number
  max_pages: number
  max_text: number
  extensions: string[]
}
export type DemoQuestion = {id: string; group: string; question: string}
export const dimensions: Dimension[] = ['member', 'date', 'department', 'disease']
