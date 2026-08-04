# AI Escalation Rule

## Antigravity Handles (70–85% of work)
- Scaffolding, standard code, tests, docs, config, bug fixes, small refactors.
- All Git operations (branch, commit, merge, tag).

## Escalate to Codex ONLY When These Criteria Are Met

### C1 — Persistent Bug
Same bug remains after **two documented** fix attempts with evidence.

### C2 — Complex Computational Geometry
Issues involving polygon topology, invalid geometry, self-intersection, DXF arc/bulge interpretation, polygon holes, or floating-point precision errors.

### C3 — Complex CRS / Coordinate Transformations
Coordinate Reference System edge cases, projection distortion, datum shifts.

### C4 — AutoCAD / ArcGIS API Compatibility
Deep compatibility issues with AutoCAD COM/.NET, AutoLISP, or ArcGIS APIs.

### C5 — Core Architecture Modification
Changes that affect the fundamental module boundary or data flow architecture.

### C6 — Test–Reality Divergence
Automated tests pass but results disagree with AutoCAD / GIS manual verification.

### C7 — Large-Scale Regression Risk
Refactors that could break multiple stable modules simultaneously.

## Escalation Protocol
When escalating, Antigravity must auto-generate `CODEX_ESCALATION.md` following the mandatory template (problem, expected vs actual behavior, minimal reproduction, related files, attempted solutions, test results, suspected root cause, modification constraints).
