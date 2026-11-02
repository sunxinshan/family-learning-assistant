import type { Vocabulary } from '../types/domain'

export const vocabularyEntryCount = (library: Vocabulary): number =>
  library.entryCount ?? library.entries.length

export const hasVocabularyDetails = (library: Vocabulary): boolean =>
  library.entriesIncluded !== false
