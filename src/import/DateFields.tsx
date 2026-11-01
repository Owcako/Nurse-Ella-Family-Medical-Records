import {Button, Input} from '@chakra-ui/react'
import {useId, useState} from 'react'
import {parseDate} from '../dates'
import type {Labels} from './strings'

// View: src/library/browsing-flow.svg#R6
// Expose separate month/day/year controls so a user can preserve incomplete dates.
// Keep the form representation separate from the report's original printed wording.
export function DateFields ({value, onChange, disabled, labels: t, valid}: {
  value: string; onChange: (value: string) => void; disabled: boolean; labels: Labels; valid: boolean
})
{
  const [parts, setParts] = useState (() => parseDate (value) ?? {month: '', day: '', year: ''})
  const [original] = useState (value)
  const help = useId ()

  // View: src/library/browsing-flow.svg#R6
  // Retain only numeric field input and rebuild the entered precision; a year is
  // needed before a month/day can identify an archive date.
  function change (key: 'month' | 'day' | 'year', value: string)
  {
    if (!/^\d*$/.test (value)) return
    const next = {...parts, [key]: value}
    setParts (next)
    // A blank day preserves month-only precision; all blanks mean unrecorded.
    // Year-first draft values ensure an invalid Month field is never re-read as a day.
    onChange (next.day ? `${next.year}-${next.month}-${next.day}` : next.month ? `${next.year}-${next.month}` : next.year)
  }

  return <fieldset className="date-fields" disabled={disabled} aria-describedby={help}>
    <legend>{t.date} <span>M/D/YYYY</span></legend>
    <div className="date-fields-row">{(['month', 'day', 'year'] as const).map (key =>
      <label key={key}>{t[key]}<Input unstyled inputMode="numeric" autoComplete="off" placeholder={key === 'year' ? 'YYYY' : key === 'month' ? 'MM' : 'DD'}
        maxLength={key === 'year' ? 4 : 2} value={parts[key]} aria-invalid={!valid} onChange={event => change (key, event.target.value)} /></label>
    )}</div>
    <small id={help}>{t.dateHelp}</small>
    {original && !parseDate (original) && <small>{t.recordedDate}: {original}</small>}
    {!valid && <small className="error-text" role="alert">{t.invalidDate}</small>}
    <Button unstyled className="quiet" type="button" disabled={disabled} onClick={() => {setParts ({month: '', day: '', year: ''}); onChange ('')}}>{t.clearDate}</Button>
  </fieldset>
}
