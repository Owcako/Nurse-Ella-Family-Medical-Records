// Year-last numeric dates use the user-selected month/day/year convention.
// Keep clearly day-first dates readable and never invent missing precision.
// View: src/library/browsing-flow.svg#R6
// Interpret supported printed dates under the month/day/year convention, while
// accepting clearly day-first dates. Validate real calendar days and preserve missing precision.
export function parseDate (value: string)
{
  let printed = value.trim ()
  const numeric = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/.exec (printed)
  if (numeric)
  {
    const first = Number (numeric[1]), second = Number (numeric[2])
    if (first > 12 && second <= 12) printed = `${numeric[3]}-${second}-${first}`
    else if (first <= 12) printed = `${numeric[3]}-${first}-${second}`
    else return null
  }
  const monthYear = /^(\d{1,2})\/(\d{4})$/.exec (printed)
  if (monthYear) printed = `${monthYear[2]}-${monthYear[1]}`
  const names = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
  const named = /^(?:(\d{1,2})\s+([a-z]+),?\s+(\d{4})|([a-z]+)\s+(\d{1,2}),?\s+(\d{4})|([a-z]+)\s+(\d{4}))$/i.exec (printed)
  if (named)
  {
    const word = (named[2] ?? named[4] ?? named[7]).toLowerCase ()
    const month = names.findIndex (name => word === name || word === name.slice (0, 3)) + 1
    if (!month) return null
    printed = `${named[3] ?? named[6] ?? named[8]}-${month}${named[1] ?? named[5] ? `-${named[1] ?? named[5]}` : ''}`
  }
  const match = /^(\d{4})(?:(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)|(?:年(?:(\d{1,2})月(?:(\d{1,2})日)?)?))?$/.exec (printed)
  if (!match) return null
  const month = Number (match[2] ?? match[4])
  const day = Number (match[3] ?? match[5])
  if (Number (match[1]) < 1) return null
  if (month && (month < 1 || month > 12)) return null
  if ((match[2] ?? match[4]) && !month) return null
  if ((match[3] ?? match[5]) && (!day || day > new Date (Number (match[1]), month, 0).getDate ())) return null
  return {year: match[1], month: month ? String (month).padStart (2, '0') : '', day: day ? String (day).padStart (2, '0') : ''}
}

// View: src/library/browsing-flow.svg#R6
// Display recognized dates consistently without supplying absent month/day values.
// Return unsupported wording unchanged so the report remains reviewable.
export function formatDate (value: string)
{
  const date = parseDate (value)
  if (!date) return value
  return date.day ? `${Number (date.month)}/${Number (date.day)}/${date.year}` : date.month ? `${Number (date.month)}/${date.year}` : date.year
}
