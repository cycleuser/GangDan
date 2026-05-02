"""Tests for preprint_categories module."""

import pytest

from gangdan.core.preprint_categories import (
    ARXIV_CATEGORIES,
    BIORXIV_CATEGORIES,
    MEDRXIV_CATEGORIES,
    PLATFORMS,
    Category,
    get_all_categories,
    get_category_by_code,
    get_platform_categories,
    search_categories,
)


class TestCategoryDataclass:
    """Test Category dataclass."""

    def test_defaults(self) -> None:
        cat = Category()
        assert cat.code == ""
        assert cat.name == ""
        assert cat.name_zh == ""

    def test_to_dict(self) -> None:
        cat = Category(code="cs.AI", name="AI", name_zh="人工智能")
        d = cat.to_dict()
        assert d["code"] == "cs.AI"
        assert d["name"] == "AI"
        assert d["name_zh"] == "人工智能"


class TestArxivCategories:
    """Test arXiv category definitions."""

    def test_has_categories(self) -> None:
        assert len(ARXIV_CATEGORIES) > 0

    def test_cs_ai_exists(self) -> None:
        codes = [c.code for c in ARXIV_CATEGORIES]
        assert "cs.AI" in codes
        assert "cs.LG" in codes
        assert "cs.CL" in codes

    def test_all_have_names(self) -> None:
        for cat in ARXIV_CATEGORIES:
            assert cat.name, f"Category {cat.code} has no name"
            assert cat.name_zh, f"Category {cat.code} has no Chinese name"


class TestBioRxivCategories:
    """Test bioRxiv category definitions."""

    def test_has_categories(self) -> None:
        assert len(BIORXIV_CATEGORIES) > 0

    def test_key_collections_exist(self) -> None:
        codes = [c.code for c in BIORXIV_CATEGORIES]
        assert "genomics" in codes
        assert "neuroscience" in codes
        assert "bioinformatics" in codes
        assert "cancer_biology" in codes

    def test_all_have_names(self) -> None:
        for cat in BIORXIV_CATEGORIES:
            assert cat.name
            assert cat.name_zh


class TestMedRxivCategories:
    """Test medRxiv category definitions."""

    def test_has_categories(self) -> None:
        assert len(MEDRXIV_CATEGORIES) > 0

    def test_key_collections_exist(self) -> None:
        codes = [c.code for c in MEDRXIV_CATEGORIES]
        assert "oncology" in codes
        assert "infectious_diseases" in codes
        assert "epidemiology" in codes
        assert "neurology" in codes

    def test_all_have_names(self) -> None:
        for cat in MEDRXIV_CATEGORIES:
            assert cat.name
            assert cat.name_zh


class TestPlatformMetadata:
    """Test platform metadata."""

    def test_three_platforms(self) -> None:
        assert "arxiv" in PLATFORMS
        assert "biorxiv" in PLATFORMS
        assert "medrxiv" in PLATFORMS

    def test_platform_has_categories(self) -> None:
        for platform, info in PLATFORMS.items():
            assert "categories" in info
            assert len(info["categories"]) > 0


class TestGetPlatformCategories:
    """Test get_platform_categories function."""

    def test_arxiv_categories(self) -> None:
        cats = get_platform_categories("arxiv")
        assert len(cats) > 0
        assert cats[0].code.startswith("cs.") or cats[0].code.startswith("math.")

    def test_biorxiv_categories(self) -> None:
        cats = get_platform_categories("biorxiv")
        assert len(cats) > 0
        assert cats[0].code == "bioinformatics"

    def test_medrxiv_categories(self) -> None:
        cats = get_platform_categories("medrxiv")
        assert len(cats) > 0

    def test_unknown_platform(self) -> None:
        cats = get_platform_categories("unknown")
        assert cats == []


class TestGetAllCategories:
    """Test get_all_categories function."""

    def test_returns_dict(self) -> None:
        result = get_all_categories()
        assert isinstance(result, dict)
        assert "arxiv" in result
        assert "biorxiv" in result
        assert "medrxiv" in result

    def test_category_structure(self) -> None:
        result = get_all_categories()
        for platform, data in result.items():
            assert "name" in data
            assert "categories" in data
            assert isinstance(data["categories"], list)
            if data["categories"]:
                assert "code" in data["categories"][0]
                assert "name" in data["categories"][0]
                assert "name_zh" in data["categories"][0]


class TestSearchCategories:
    """Test search_categories function."""

    def test_search_by_code(self) -> None:
        results = search_categories("cs.AI")
        assert len(results) > 0
        assert results[0]["code"] == "cs.AI"

    def test_search_by_name(self) -> None:
        results = search_categories("machine learning")
        assert len(results) > 0
        codes = [r["code"] for r in results]
        assert "cs.LG" in codes or "cs.AI" in codes

    def test_search_by_chinese_name(self) -> None:
        results = search_categories("人工智能")
        assert len(results) > 0
        assert results[0]["code"] == "cs.AI"

    def test_search_platform_filter(self) -> None:
        results = search_categories("genomics", platform="biorxiv")
        assert len(results) > 0
        for r in results:
            assert r["platform"] == "biorxiv"

    def test_search_no_results(self) -> None:
        results = search_categories("xyznonexistent123")
        assert results == []

    def test_search_description_match(self) -> None:
        results = search_categories("deep learning")
        assert len(results) > 0


class TestGetCategoryByCode:
    """Test get_category_by_code function."""

    def test_find_arxiv_category(self) -> None:
        cat = get_category_by_code("cs.AI", "arxiv")
        assert cat is not None
        assert cat.name == "Artificial Intelligence"

    def test_find_biorxiv_category(self) -> None:
        cat = get_category_by_code("genomics", "biorxiv")
        assert cat is not None
        assert cat.name == "Genomics"

    def test_not_found(self) -> None:
        cat = get_category_by_code("nonexistent", "arxiv")
        assert cat is None

    def test_wrong_platform(self) -> None:
        cat = get_category_by_code("cs.AI", "biorxiv")
        assert cat is None
