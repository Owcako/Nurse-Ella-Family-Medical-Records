"""Exact family identity matching; no fuzzy guesses about patient names."""


# View: backend/library-storage.svg#S8
# Normalize whitespace and case for exact comparison without changing the report wording.
def normalized_name(value):
    return " ".join(value.split()).casefold()


# View: backend/library-storage.svg#S8
# Return a profile only when exactly one normalized name/alias matches.
# Zero or multiple matches remain unresolved so family histories are not merged by guesswork.
def match_profile(value, profiles):
    name = normalized_name(value)
    matches = [profile for profile in profiles if name in
               [normalized_name(item) for item in [profile["name"], *profile["aliases"]]]]
    return matches[0] if name and len(matches) == 1 else None
