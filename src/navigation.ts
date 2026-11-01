export type Page = 'records' | 'chat'

export function fileFromHash (hash: string)
{
  if (!hash.startsWith ('#/files/')) return null
  try {return decodeURIComponent (hash.slice (8))}
  catch {return hash.slice (8)}
}

export function pageFromHash (hash: string): Page
{
  if (hash === '#chat') return 'chat'
  if (hash === '#records' || fileFromHash (hash)) return 'records'
  return 'records'
}

export function canonicalHash (hash: string)
{
  return hash === '#records' || hash === '#chat' || fileFromHash (hash) ? hash : '#records'
}
