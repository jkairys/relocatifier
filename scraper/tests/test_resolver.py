"""Slug-resolution tests with a fake sitemap + fake metrics.json (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scraper.resolver import (
    SalNotFoundError,
    SlugResolutionError,
    parse_oth_sitemap,
    resolve_slug,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseSitemap:
    def setup_method(self):
        self.by_key = parse_oth_sitemap((FIXTURES / "oth_sitemap.xml").read_text())

    def test_keys_by_name_and_state(self):
        assert self.by_key[("BLI BLI", "QLD")] == ["bli-bli-4560"]

    def test_same_name_different_state_separated(self):
        assert ("NEWTOWN", "NSW") in self.by_key
        assert ("NEWTOWN", "QLD") in self.by_key
        assert self.by_key[("NEWTOWN", "NSW")] == ["newtown-2042"]

    def test_ambiguous_within_state_groups(self):
        assert len(self.by_key[("NEWTOWN", "QLD")]) == 2
        assert len(self.by_key[("BUDERIM", "QLD")]) == 2


def _resolve(sal_code: str):
    return resolve_slug(
        sal_code,
        metrics_path=FIXTURES / "metrics.json",
        sitemap_cache_path=FIXTURES / "oth_sitemap.xml",
    )


class TestResolveSlug:
    def test_single_match_resolves(self):
        resolved = _resolve("30900")  # Bli Bli QLD
        assert resolved.oth_slug == "bli-bli-4560"
        assert resolved.postcode == "4560"
        assert resolved.state == "QLD"
        assert resolved.name == "Bli Bli"

    def test_cross_state_disambiguation(self):
        # Newtown NSW resolves even though a QLD Newtown exists, because the
        # state scopes the match.
        resolved = _resolve("12042")
        assert resolved.oth_slug == "newtown-2042"

    def test_ambiguous_within_state_refused(self):
        with pytest.raises(SlugResolutionError) as exc:
            _resolve("39999")  # Newtown QLD — two slugs
        assert sorted(exc.value.candidates) == ["newtown-4305", "newtown-4350"]
        assert "issue #2" in str(exc.value)

    def test_ambiguous_buderim_refused(self):
        with pytest.raises(SlugResolutionError) as exc:
            _resolve("31234")
        assert len(exc.value.candidates) == 2

    def test_no_candidate_refused(self):
        with pytest.raises(SlugResolutionError) as exc:
            _resolve("49999")  # Nowhereville — not in sitemap
        assert exc.value.candidates == []

    def test_unknown_sal_not_found(self):
        with pytest.raises(SalNotFoundError):
            _resolve("99999")
