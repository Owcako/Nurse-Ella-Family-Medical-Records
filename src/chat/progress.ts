export type ChatProgress = {stage: 'preparing' | 'searching' | 'reading' | 'reading_original' | 'answering' | 'reviewing'; count?: number}

// A single POST carries live stage receipts followed by the fully reviewed answer.
// An interrupted stream fails visibly; never retry a paid AI operation implicitly.
export async function requestChat<T> (options: RequestInit, onProgress: (progress: ChatProgress) => void): Promise<T>
{
  const response = await fetch ('/api/chat', {...options, headers: {...options.headers, Accept: 'application/x-ndjson'}})
  if (!response.ok)
  {
    const body = await response.json ().catch (() => null)
    throw new Error (typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status}).`)
  }
  // Keep compatibility with JSON servers and existing read-only test fixtures.
  if (!response.headers.get ('Content-Type')?.includes ('application/x-ndjson')) return response.json ()
  const reader = response.body!.getReader ()
  const decoder = new TextDecoder ()
  let pending = ''
  function consume (line: string): {result: T} | undefined
  {
    if (!line.trim ()) return
    const event = JSON.parse (line)
    if (event.type === 'error') throw new Error (event.detail)
    if (event.type === 'status') onProgress ({stage: event.stage, count: event.count})
    if (event.type === 'result') return {result: event.result}
  }
  try
  {
    while (true)
    {
      const {value, done} = await reader.read ()
      pending += decoder.decode (value, {stream: !done})
      let end = pending.indexOf ('\n')
      while (end >= 0)
      {
        const receipt = consume (pending.slice (0, end))
        pending = pending.slice (end + 1)
        if (receipt) return receipt.result
        end = pending.indexOf ('\n')
      }
      if (done)
      {
        const receipt = consume (pending)
        if (receipt) return receipt.result
        throw new Error ('The connection ended before the answer was complete. Please retry.')
      }
    }
  }
  finally {await reader.cancel ().catch (() => {}); reader.releaseLock ()}
}
