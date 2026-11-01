// Architecture: ../../implementation-architecture.svg#O2; ui-flow.svg#U4.
// Shared HTTP boundary: failed/unreachable requests never become success receipts.
// View: implementation-architecture.svg#O2
// Use the same-origin /api boundary for both development and hosting.
// Network/non-2xx responses throw: callers must not interpret an uncertain action as saved.
export async function request<T> (path: string, options?: RequestInit): Promise<T>
{
  let response: Response
  try
  {
    response = await fetch ('/api' + path, options)
  }
  catch
  {
    throw new Error ('The backend is unreachable. Your action is not confirmed. Check the connection and retry.')
  }
  if (!response.ok)
  {
    const body = await response.json ().catch (() => null)
    throw new Error (typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status}).`)
  }
  return response.status === 204 ? undefined as T : response.json ()
}

// View: implementation-architecture.svg#O7
// Build JSON request bodies consistently; endpoint validation remains on the backend.
export function json (body: unknown): RequestInit
{
  return {headers: {'Content-Type': 'application/json'}, body: JSON.stringify (body)}
}

// View: src/import/ui-flow.svg#U4
// Upload keys need secure random bytes, not the secure-context-only randomUUID API.
// getRandomValues also works on a plain HTTP server address; retain the resulting key
// for retries so an uncertain response cannot create another stored document.
export function operationKey ()
{
  return Array.from (crypto.getRandomValues (new Uint8Array (16)), value => value.toString (16).padStart (2, '0')).join ('')
}
