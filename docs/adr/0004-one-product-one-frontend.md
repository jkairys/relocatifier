# One product, one frontend

Relocatifier has a single frontend. Acquisition services (listings scraper, NAPLAN scraper) are driven from inside it — defining Watchlists, triggering runs, browsing results — rather than through separate admin UIs. The predecessor accumulated three disconnected UIs (school map, oth-admin, analytics notebooks) that never integrated; the lesson recorded here is that the split was the mess, not any one UI. A future contributor tempted to "quickly add an admin page" to a service should extend the main frontend instead.

## Consequences

- Watchlist mode requires the frontend to talk to a locally running scraper service; Discovery mode remains fully static (ADR-0002). The frontend degrades gracefully when no service is running.
- The scraper's mission is narrowed to match: OnTheHouse only, historical research (sold prices, price history, time-on-market) where a decent sample suffices. Live listings enter only via hand-imported Starred Listings — bulk-scraping live portals (REA, Domain) is explicitly out of scope.
