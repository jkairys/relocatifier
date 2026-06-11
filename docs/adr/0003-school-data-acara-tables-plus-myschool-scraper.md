# School data: ACARA bulk tables for identity/profile, MySchool scraper for NAPLAN only

School identity, location (lat/long, SA1–SA4, LGA), ICSEA, enrolments and sector come from ACARA's freely downloadable School Profile and School Location tables (verified June 2026: direct download, no registration, ~9,755 schools, keyed by ACARA ID). Per-school NAPLAN scores are NOT in any free download — ACARA's Data Access Program requires an ABN-holding organisation and excludes school-ranking use, and state portals redirect to MySchool — so the predecessor's MySchool scraper is retained for NAPLAN scores only, slimmed to fetch scores keyed by ACARA ID.

## Consequences

- The scraper's name-matching/geocoding code is deleted, not fixed — identity and location come from the official tables (see ADR-0001).
- Re-verify the free-download landscape before extending the scraper: this was checked hands-on in June 2026 and is the kind of thing that changes.
