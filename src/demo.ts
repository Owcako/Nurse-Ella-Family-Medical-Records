import type {MedicalFile, Profile} from './import/types'
import kit from '../backend/demo-kit/manifest.json'

// Shared resets replace document IDs. Follow the prepared source filenames so a
// tab does not keep waiting for IDs that another client has already replaced.
export function demoDocuments (files: MedicalFile[])
{
  return kit.files.map (name => files.find (file => file.original_filename === name)).filter ((file): file is MedicalFile => Boolean (file))
}

export function isLiveDemoFile (file: MedicalFile)
{
  return Boolean (file.original_filename && kit.live_files.includes (file.original_filename))
}

// Existing demo imports may retain the report's surname-first display name.
export function demoMember (profiles: Profile[])
{
  return profiles.find (profile => [profile.name, ...profile.aliases].some (name =>
    ['john smith', 'smith, john'].includes (name.trim ().replace (/\s+/g, ' ').toLowerCase ())))
}
