# Coding Discipline Rule

- **One Requirement, One Module**: Work on one isolated capability at a time.
- **Freeze Stable Modules**: Modules marked STABLE with passed tests must not be modified without explicit bug rationale.
- **No Hardcoded Planning Standards**: Standards (FAR limits, setbacks, densities) must be placed in external configuration files (e.g. YAML/JSON) with source/city metadata.
- **Small Commits**: Maintain focused, atomic git commits that are easy to audit or rollback.
