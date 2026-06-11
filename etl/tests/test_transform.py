"""Unit tests for the pure transformation logic — no downloads required."""

import pytest

from relocatifier_etl.transform import (
    display_name,
    metric_stats,
    normalise_sal_code,
    pct_children,
)


class TestNormaliseSalCode:
    def test_datapack_form(self):
        assert normalise_sal_code("SAL10001") == "10001"

    def test_bare_form_passthrough(self):
        assert normalise_sal_code("10001") == "10001"

    def test_whitespace_stripped(self):
        assert normalise_sal_code(" SAL31022 ") == "31022"

    @pytest.mark.parametrize("bad", ["", "SAL1", "1000", "100001", "POA4551", "Bli Bli"])
    def test_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            normalise_sal_code(bad)


class TestDisplayName:
    def test_state_suffix_stripped(self):
        assert display_name("Richmond (NSW)") == "Richmond"
        assert display_name("Richmond (Qld)") == "Richmond"

    def test_region_state_suffix_stripped(self):
        assert display_name("Karrabin (Ipswich - Qld)") == "Karrabin"

    def test_plain_name_untouched(self):
        assert display_name("Bli Bli") == "Bli Bli"

    def test_non_state_parenthetical_kept(self):
        # Parentheticals that aren't state disambiguation must survive.
        assert display_name("St Leonards (Vic.)") == "St Leonards (Vic.)"


class TestPctChildren:
    def test_basic_one_decimal(self):
        # (120 + 280) / 2000 * 100 = 20.0
        assert pct_children(120, 280, 2000) == 20.0

    def test_rounds_to_one_decimal(self):
        assert pct_children(1, 2, 7) == 42.9

    def test_zero_population_is_null(self):
        assert pct_children(0, 0, 0) is None

    def test_null_population_is_null(self):
        assert pct_children(10, 10, None) is None

    def test_null_components_are_null(self):
        assert pct_children(None, 10, 100) is None


class TestMetricStats:
    def test_known_values(self):
        stats = metric_stats(list(range(1, 12)))  # 1..11
        assert stats["median"] == 6
        assert stats["p10"] == 2
        assert stats["p90"] == 10

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            metric_stats([])
