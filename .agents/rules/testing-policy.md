# Testing Policy Rule

- **Test First & Gold Standard**: Every core spatial calculation module requires unit tests including normal cases, edge cases, error cases, topology anomalies, and unit verification.
- **Gold Standard Fixtures**: Maintain canonical fixtures (GS-001 through GS-005) that remain unchanged to catch regressions.
- **Automated Verification**: Build commands must pass pytest before merging into `main`.
