"""Tests for DBLPFetcher."""

from unittest.mock import MagicMock, patch

from gangdan.core.research_searcher import DBLPFetcher


class TestDBLPFetcher:
    """Test DBLPFetcher functionality."""

    def test_dblp_fetcher_init(self):
        """Test fetcher initialization."""
        fetcher = DBLPFetcher(timeout=10, max_results=5)
        assert fetcher.name == "dblp"
        assert fetcher.timeout == 10
        assert fetcher.max_results == 5

    def test_dblp_search_success(self):
        """Test successful search with valid response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "@total": "100",
                    "@sent": "1",
                    "@start": "0",
                    "hit": [
                        {
                            "info": {
                                "title": "Attention Is All You Need",
                                "year": "2017",
                                "doi": "10.5555/3295222.3295349",
                                "url": "https://proceedings.neurips.cc/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html",
                                "ee": "https://arxiv.org/abs/1706.03762",
                                "venue": "NeurIPS",
                                "authors": {
                                    "author": [
                                        {"text": "Ashish Vaswani"},
                                        {"text": "Noam Shazeer"},
                                    ]
                                },
                            }
                        }
                    ],
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(DBLPFetcher, "__init__", lambda self, **kw: None):
            fetcher = DBLPFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("attention mechanism")

        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "Attention Is All You Need"
        assert paper.year == 2017
        assert paper.doi == "10.5555/3295222.3295349"
        assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
        assert paper.source == "dblp"
        assert paper.url == "https://proceedings.neurips.cc/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html"
        assert paper.journal == "NeurIPS"
        assert paper.venue == "NeurIPS"

    def test_dblp_search_empty_response(self):
        """Test search with empty results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"hits": {"hit": []}}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(DBLPFetcher, "__init__", lambda self, **kw: None):
            fetcher = DBLPFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("nonexistent query")

        assert len(papers) == 0

    def test_dblp_search_api_error(self):
        """Test search with API error."""
        with patch.object(DBLPFetcher, "__init__", lambda self, **kw: None):
            fetcher = DBLPFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.side_effect = Exception("Connection failed")

            papers = fetcher.search("test")

        assert len(papers) == 0

    def test_dblp_search_single_author_dict(self):
        """Test handling of single author as dict instead of list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Single Author Paper",
                                "year": "2023",
                                "authors": {"author": {"text": "John Doe"}},
                            }
                        }
                    ]
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(DBLPFetcher, "__init__", lambda self, **kw: None):
            fetcher = DBLPFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("test")

        assert len(papers) == 1
        assert papers[0].authors == ["John Doe"]

    def test_dblp_search_pdf_url_from_ee(self):
        """Test PDF URL extraction from ee field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "PDF Paper",
                                "year": "2023",
                                "ee": "https://example.com/paper.pdf",
                                "authors": {"author": []},
                            }
                        }
                    ]
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(DBLPFetcher, "__init__", lambda self, **kw: None):
            fetcher = DBLPFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("test")

        assert len(papers) == 1
        assert papers[0].pdf_url == "https://example.com/paper.pdf"

    def test_dblp_search_missing_fields(self):
        """Test handling of missing/null fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Minimal Paper",
                            }
                        }
                    ]
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(DBLPFetcher, "__init__", lambda self, **kw: None):
            fetcher = DBLPFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("test")

        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "Minimal Paper"
        assert paper.year == 0
        assert paper.authors == []
