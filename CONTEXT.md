# Relocatifier

A personal research platform for deciding where to relocate a family along Australia's east coast: shortlist suburbs from high-level comparable data, then zoom into candidates with fresher, deeper data.

## Language

**Suburb**:
The unit of analysis — a gazetted suburb/locality as defined by the ABS "Suburbs and Localities" (SAL) boundary set, identified by its SAL code.
_Avoid_: locality, area, neighbourhood

**SAL code**:
The stable ABS identifier for a Suburb; the universal join key across all datasets. Joining datasets by suburb *name* is banned (see ADR-0001).

**Search Zone**:
The geography under active research: coastal QLD and NSW, from Cairns down to the Batemans Bay area. Victoria is explicitly out. Cheap uniform datasets may be ingested nationally; the Search Zone bounds where acquisition *effort* is spent.

**Metric**:
A single per-Suburb attribute used for comparison — median age, median house price, median rent, yield, crime rate, climate averages, school quality.

**Discovery**:
The 10,000-foot research mode: comparing Metrics across every Suburb in the Search Zone (choropleth maps, stat sheets) to produce a shortlist. Tolerates stale-but-consistent data.

**Watchlist**:
A set of shortlisted Suburbs that receive fresher, deeper data collection — recent sales, live listings, property-to-school proximity. The zoom-in mode that follows Discovery.

**School**:
A campus identified by its ACARA ID, with location and profile (ICSEA, enrolments, sector) taken from ACARA's official tables. School names are display labels, never identifiers.

**Catchment**:
The polygon of addresses entitled to enrol at a state School.
_Avoid_: intake zone (NSW terminology), zone
