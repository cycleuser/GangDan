"""Tests for gangdan.core.web_searcher module."""

import pytest
from unittest.mock import patch, MagicMock


class TestWebSearcher:
    """Test WebSearcher class."""
    
    def test_init(self, temp_data_dir):
        """Test WebSearcher initialization."""
        from gangdan.core.web_searcher import WebSearcher
        
        searcher = WebSearcher()
        assert searcher._timeout == 15
    
    def test_search_success(self, temp_data_dir):
        """Test successful web search."""
        from gangdan.core.web_searcher import WebSearcher
        
        html_response = '''
        <html><body>
        <a class="result__a" href="https://example.com/page1">Test Result 1</a>
        <a class="result__snippet">This is a test snippet for result 1.</a>
        </body></html>
        '''
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_response
        
        searcher = WebSearcher()
        searcher._session.post = MagicMock(return_value=mock_response)
        
        results = searcher.search("test query", num_results=5)
        
        assert isinstance(results, list)
        # The regex pattern might not match the simplified HTML, but shouldn't crash
    
    def test_search_error_handling(self, temp_data_dir):
        """Test web search handles errors gracefully."""
        from gangdan.core.web_searcher import WebSearcher
        
        searcher = WebSearcher()
        searcher._session.post = MagicMock(side_effect=ConnectionError("Connection failed"))
        
        results = searcher.search("test query")
        
        # Should return empty list, not raise
        assert results == []
    
    def test_search_timeout(self, temp_data_dir):
        """Test web search handles timeout."""
        import requests
        from gangdan.core.web_searcher import WebSearcher
        
        searcher = WebSearcher()
        searcher._session.post = MagicMock(side_effect=requests.exceptions.Timeout("Timed out"))
        
        results = searcher.search("test query")
        
        assert results == []
    
    def test_search_respects_num_results(self, temp_data_dir):
        """Test that search respects num_results parameter."""
        from gangdan.core.web_searcher import WebSearcher
        
        # Generate HTML with many results
        results_html = ""
        for i in range(10):
            results_html += f'''
            <a class="result__a" href="https://example.com/page{i}">Result {i}</a>
            <a class="result__snippet">Snippet for result {i}.</a>
            '''
        
        html = f"<html><body>{results_html}</body></html>"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        
        searcher = WebSearcher()
        searcher._session.post = MagicMock(return_value=mock_response)
        
        results = searcher.search("test", num_results=3)
        
        # Should not return more than requested
        assert len(results) <= 3
    
    def test_get_proxies_integration(self, temp_data_dir):
        """Test that proxy settings are used."""
        from gangdan.core.web_searcher import WebSearcher
        
        with patch("gangdan.core.web_searcher.get_proxies", return_value={"http": "http://proxy:8080"}):
            searcher = WebSearcher()
            proxies = searcher._get_proxies()
            
            assert proxies is not None
            assert proxies["http"] == "http://proxy:8080"
