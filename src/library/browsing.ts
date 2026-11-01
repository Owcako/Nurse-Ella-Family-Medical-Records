import {parseDate} from '../dates'
import type {Dimension, MedicalFile, Profile} from '../import/types'

export const requiredDimensions: Dimension[] = ['member', 'date', 'department']
export type MemberOption = {id: string; name: string}
export type FileGroup = {id: string; value: string; placement: 'confirmed' | 'unknown' | 'tentative'; files: MedicalFile[]}
export type FileBranch = FileGroup & {kind?: 'year' | 'month' | 'unknown-month' | 'unparsed-date'; children?: FileBranch[]}

// View: src/library/browsing-flow.svg#R6
// Reuse the shared date parser so tree grouping and viewer date handling agree.
export function dateParts (value: string)
{
  const date = parseDate (value)
  return date ? {year: date.year, month: date.month} : null
}

// View: src/library/browsing-flow.svg#R4
// Build year/month nodes only from confirmed parseable dates. Keep month-less
// years and unparseable dates visible, sort recognized dates chronologically, and deduplicate counts.
export function fileBranches (groups: FileGroup[], dimension: Dimension): FileBranch[]
{
  if (dimension !== 'date') return groups
  const years = new Map<string, FileBranch> ()
  const other: FileBranch[] = []
  const chronology = [...groups].sort ((a, b) => {
    const first = parseDate (a.value), second = parseDate (b.value)
    return first && second ? `${second.year}${second.month}${second.day}`.localeCompare (`${first.year}${first.month}${first.day}`) : first ? -1 : second ? 1 : 0
  })
  for (const group of chronology)
  {
    const date = group.placement === 'confirmed' ? dateParts (group.value) : null
    if (!date)
    {
      if (group.placement !== 'confirmed') {other.push (group); continue}
      let unresolved = other.find (item => item.kind === 'unparsed-date')
      if (!unresolved)
      {
        unresolved = {id: 'unparsed-dates', value: '', placement: 'unknown', kind: 'unparsed-date', files: []}
        other.push (unresolved)
      }
      for (const file of group.files) if (!unresolved.files.some (item => item.id === file.id)) unresolved.files.push (file)
      continue
    }
    if (!years.has (date.year)) years.set (date.year, {id: `year:${date.year}`, value: date.year, placement: 'confirmed', kind: 'year', files: [], children: []})
    const year = years.get (date.year)!
    const id = `month:${date.year}:${date.month}`
    let month = year.children!.find (item => item.id === id)
    if (!month)
    {
      month = {id, value: date.month, placement: 'confirmed', kind: date.month ? 'month' : 'unknown-month', files: []}
      year.children!.push (month)
    }
    for (const file of group.files)
    {
      if (!year.files.some (item => item.id === file.id)) year.files.push (file)
      if (!month.files.some (item => item.id === file.id)) month.files.push (file)
    }
  }
  for (const year of years.values ()) year.children!.sort ((a, b) => b.value.localeCompare (a.value))
  return [...years.values ()].sort ((a, b) => b.value.localeCompare (a.value)).concat (other)
}

// View: src/library/browsing-flow.svg#R2
// Missing member/date/department facts require review; absence of a disease label
// is not itself an error that forces the app to invent a diagnosis.
export function unresolvedFields (file: MedicalFile)
{
  return requiredDimensions.filter (key => file.metadata?.[key].status !== 'known' || !file.metadata[key].values.length)
}

// View: src/library/browsing-flow.svg#R2
// Combine independent review reasons instead of letting successful filing hide
// failed checking, suspect text, unresolved fields or an outdated evidence index.
export function needsAttention (file: MedicalFile)
{
  return unresolvedFields (file).length > 0 || file.status !== 'filed' || file.extraction_status === 'failed' ||
    file.concerns.some (concern => !concern.reviewed) || file.check_status !== 'checked' || file.archive.index_state !== 'current'
}

// Only confirmed patient names can link a report to a profile. An exact name/alias
// must identify a single profile; ambiguous patient candidates never match a filter.
// View: src/library/browsing-flow.svg#R1
// Resolve only a confirmed single patient name against profile ID or exact aliases.
// Ambiguous candidates never enter a managed member filter by fuzzy similarity.
export function memberIdentity (file: MedicalFile, profiles: Profile[])
{
  const field = file.metadata?.member
  if (field?.status !== 'known' || field.values.length !== 1) return ''
  const value = field.values[0]
  const normalized = (name: string) => name.trim ().replace (/\s+/g, ' ').toLowerCase ()
  const matches = profiles.filter (profile => [profile.name, ...profile.aliases].some (name => normalized (name) === normalized (value.value)))
  const profile = profiles.find (profile => profile.id === value.profile_id) ?? (matches.length === 1 ? matches[0] : undefined)
  return profile ? `profile:${profile.id}` : ''
}

// View: src/library/browsing-flow.svg#R5
// A clearly printed but unmanaged name is reviewable without blocking archival.
export function needsMemberReview (file: MedicalFile, profiles: Profile[])
{
  return file.status === 'filed' && file.metadata?.member.status === 'known' && file.metadata.member.values.length === 1 && !memberIdentity (file, profiles)
}

// View: src/library/browsing-flow.svg#R5
// Include both ID and detected name: a later correction/new name should trigger review again.
export function memberReviewKey (file: MedicalFile)
{
  return JSON.stringify ([file.id, file.metadata?.member.values[0]?.value])
}

// View: src/library/browsing-flow.svg#R1
// Build explicit managed-profile choices, retaining stable IDs even if display names change.
export function memberOptions (profiles: Profile[]): MemberOption[]
{
  return profiles.map (profile => ({id: `profile:${profile.id}`, name: profile.name})).sort ((a, b) => a.name.localeCompare (b.name))
}

// View: src/library/browsing-flow.svg#R3
// Separate confirmed, unknown and tentative placement. A file may appear under
// multiple supported categories, but never twice within one group.
export function groupFiles (files: MedicalFile[], dimension: Dimension, profiles: Profile[] = []): FileGroup[]
{
  // View: AGENTS.svg#F4G
  // A shared folder is only a documented category. Keep uncertain candidates separate;
  // grouping must not turn coincidental labels into a clinical or patient relationship.
  const groups = new Map<string, FileGroup> ()
  function add (file: MedicalFile, value: string, placement: FileGroup['placement'], identity = value)
  {
    const id = JSON.stringify ([placement, identity])
    if (!groups.has (id)) groups.set (id, {id, value, placement, files: []})
    const group = groups.get (id)!
    if (!group.files.some (item => item.id === file.id)) group.files.push (file)
  }
  for (const file of files)
  {
    if (dimension === 'member')
    {
      const identity = memberIdentity (file, profiles)
      const profile = profiles.find (profile => identity === `profile:${profile.id}`)
      add (file, profile?.name ?? '', profile ? 'confirmed' : 'unknown', identity)
      continue
    }
    const field = file.metadata?.[dimension]
    if (field?.status === 'known' && field.values.length)
    {
      for (const value of field.values) add (file, value.value, 'confirmed')
    }
    else
    {
      add (file, '', 'unknown')
      // Dates remain outside the confirmed chronology, including candidate dates.
      for (const value of field?.candidates ?? []) add (file, value.value, 'tentative')
    }
  }
  const order = {confirmed: 0, unknown: 1, tentative: 2}
  return [...groups.values ()].sort ((a, b) => order[a.placement] - order[b.placement] ||
    // Preserve printed precision and wording; do not parse partial dates into days.
    (dimension === 'date' && a.placement === 'confirmed' ? b.value.localeCompare (a.value) : a.value.localeCompare (b.value)))
}
