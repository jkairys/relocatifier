# Suburb = ABS SAL; all joins by stable ID, never by name

Every dataset in the system is keyed to the ABS SAL (Suburbs and Localities) code as the canonical suburb identifier, and schools are keyed by ACARA ID. Joining by name is banned. The predecessor project (school-map) joined scraped school data to geometries by fuzzy name-matching, which silently corrupted its NAPLAN dataset (schools matched to wrong-state namesakes, error strings stored as data) — this ADR exists so that mistake is structural, not just remembered.

## Consequences

- Datasets published at other units (NSW rental bonds by postcode, some ABS series at SA2) require an explicit crosswalk to SAL, and the resulting metrics are labelled as approximated rather than silently joined.
- SAL was chosen over SA2 because it matches the human/real-estate notion of "suburb"; where a richer dataset only exists at SA2, we map it rather than abandon the suburb as the unit.
