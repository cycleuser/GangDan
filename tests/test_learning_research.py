"""Tests for gangdan.learning.research module."""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime


class MockOllamaClient:
    """Mock Ollama client for testing."""
    
    def __init__(self):
        self._stop_flag = False
        self.call_count = 0
    
    def stop_generation(self):
        self._stop_flag = True
    
    def reset_stop(self):
        self._stop_flag = False
    
    def is_stopped(self):
        return self._stop_flag
    
    def chat_complete(self, messages, model, temperature=0.7):
        self.call_count += 1
        # Return different responses based on message content
        content = messages[0]["content"] if messages else ""
        content_lower = content.lower()
        
        # Check for decompose/subtopics first (more specific)
        if "decompose" in content_lower or ("subtopics" in content_lower and "report outline" not in content_lower):
            return json.dumps({
                "subtopics": [
                    {"title": "Introduction", "overview": "Overview of the topic"},
                    {"title": "Key Concepts", "overview": "Main concepts"},
                    {"title": "Applications", "overview": "Real-world applications"},
                ]
            })
        elif "report outline" in content_lower or "planning expert" in content_lower:
            return json.dumps({
                "sections": [
                    {"title": "Introduction", "instruction": "Introduce the topic"},
                    {"title": "Key Concepts", "instruction": "Explain main concepts"},
                    {"title": "Conclusion", "instruction": "Summarize findings"},
                ]
            })
        elif "refine" in content_lower or "optimization expert" in content_lower:
            return "Improved research topic"
        elif "evaluate" in content_lower:
            return json.dumps({"sufficient": True, "weak_subtopics": []})
        elif "summarize" in content_lower:
            return "This is a summary of the research notes."
        else:
            return json.dumps({"sections": [{"title": "Default", "instruction": "Default section"}]})
    
    def chat_stream(self, messages, model, temperature=0.7):
        """Yield mock streaming content."""
        self.call_count += 1
        content = "This is a detailed section about the topic. " * 20
        for i in range(0, len(content), 20):
            if self._stop_flag:
                break
            yield content[i:i+20]


class MockChromaManager:
    """Mock ChromaDB manager for testing."""
    
    def __init__(self):
        self.collections = ["test_kb"]
    
    def search(self, collection_name, query, n_results=10):
        return {
            "ids": [["doc1", "doc2"]],
            "documents": [["Test document 1 content", "Test document 2 content"]],
            "metadatas": [[{"file": "test.md"}, {"file": "test2.md"}]],
            "distances": [[0.1, 0.2]],
        }


class MockConfig:
    """Mock configuration for testing."""
    
    chat_model = "test-model"
    embedding_model = "test-embed"
    language = "en"
    top_k = 5


class TestResearchPipeline:
    """Test the research pipeline functions."""
    
    def test_rephrase_topic(self, temp_data_dir):
        """Test topic rephrasing."""
        from gangdan.learning.research import _rephrase_topic
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        result = _rephrase_topic("test topic", "en", ollama, config)
        assert result == "Improved research topic"
    
    def test_decompose_topic(self, temp_data_dir):
        """Test topic decomposition into subtopics."""
        from gangdan.learning.research import _decompose_topic
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        subtopics = _decompose_topic("test topic", 3, "en", ollama, config)
        assert len(subtopics) == 3
        assert subtopics[0].title == "Introduction"
        assert subtopics[1].title == "Key Concepts"
    
    def test_generate_outline(self, temp_data_dir):
        """Test outline generation."""
        from gangdan.learning.research import _generate_outline
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        notes = "Test notes for outline generation"
        outline = _generate_outline("test topic", notes, "en", ollama, config)
        
        assert len(outline) == 3
        assert outline[0]["title"] == "Introduction"
    
    def test_write_section_stream(self, temp_data_dir):
        """Test section streaming."""
        from gangdan.learning.research import _write_section_stream
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        content = ""
        for chunk in _write_section_stream(
            "Test Section", "Write about test", "Test notes", "en", ollama, config
        ):
            content += chunk
        
        assert len(content) > 0
        assert "detailed section" in content.lower()
    
    def test_summarize_subtopic(self, temp_data_dir):
        """Test subtopic summarization."""
        from gangdan.learning.research import _summarize_subtopic
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        result = _summarize_subtopic(
            "Test Topic", "Overview text", "RAG content here", "en", ollama, config
        )
        
        assert result is not None
        assert len(result) > 0


class TestResearchRun:
    """Test the full research run pipeline."""
    
    def test_run_research_quick(self, temp_data_dir):
        """Test quick research run."""
        from gangdan.learning.research import run_research
        
        ollama = MockOllamaClient()
        chroma = MockChromaManager()
        config = MockConfig()
        
        events = list(run_research(
            "test topic",
            ["test_kb"],
            "quick",
            ollama,
            chroma,
            config,
            save_dir=temp_data_dir
        ))
        
        # Check that we got events
        assert len(events) > 0
        
        # Check event types
        event_types = [e.get("type") for e in events]
        assert "phase" in event_types
        assert "status" in event_types
        assert "subtopic" in event_types
        assert "content" in event_types
        assert "done" in event_types
        
        # Check phases
        phases = [e.get("phase") for e in events if e.get("type") == "phase"]
        assert "rephrasing" in phases
        assert "planning" in phases
        assert "researching" in phases
        assert "reporting" in phases
        
        # Check that content was generated
        content_events = [e for e in events if e.get("type") == "content"]
        total_content = "".join(e.get("content", "") for e in content_events)
        assert len(total_content) > 0
    
    def test_run_research_with_stop(self, temp_data_dir):
        """Test research stop functionality."""
        from gangdan.learning.research import run_research
        
        ollama = MockOllamaClient()
        chroma = MockChromaManager()
        config = MockConfig()
        
        # Start research and stop after a few events
        event_count = 0
        for event in run_research(
            "test topic",
            ["test_kb"],
            "quick",
            ollama,
            chroma,
            config,
            save_dir=temp_data_dir
        ):
            event_count += 1
            if event_count > 5:
                ollama.stop_generation()
        
        assert event_count > 0


class TestResearchReportPersistence:
    """Test research report saving and loading."""
    
    def test_save_and_load_report(self, temp_data_dir):
        """Test saving and loading a research report."""
        from gangdan.learning.models import ResearchReport, ResearchSubtopic, Citation, generate_id
        from datetime import datetime
        
        report_id = generate_id("research_")
        report = ResearchReport(
            report_id=report_id,
            topic="Test Topic",
            kb_names=["test_kb"],
            depth="medium",
            created_at=datetime.now().isoformat(),
            subtopics=[
                ResearchSubtopic(title="Subtopic 1", overview="Overview 1", notes="Notes 1"),
                ResearchSubtopic(title="Subtopic 2", overview="Overview 2", notes="Notes 2"),
            ],
            citations=[
                Citation(citation_id="[1]", source_file="test.md", collection_name="test_kb"),
            ],
            report_markdown="# Test Report\n\nContent here.",
        )
        
        # Save
        report.save(temp_data_dir)
        saved_path = temp_data_dir / f"{report_id}.json"
        assert saved_path.exists()
        
        # Load
        loaded = ResearchReport.load(saved_path)
        assert loaded.report_id == report_id
        assert loaded.topic == "Test Topic"
        assert len(loaded.subtopics) == 2
        assert len(loaded.citations) == 1
    
    def test_list_reports(self, temp_data_dir):
        """Test listing saved reports."""
        from gangdan.learning.research import list_reports
        from gangdan.learning.models import ResearchReport, ResearchSubtopic
        from datetime import datetime
        
        # Create a couple of reports
        for i in range(3):
            report = ResearchReport(
                report_id=f"research_test_{i}",
                topic=f"Test Topic {i}",
                kb_names=["test_kb"],
                depth="medium",
                created_at=datetime.now().isoformat(),
                subtopics=[ResearchSubtopic(title="Test", overview="")],
                citations=[],
                report_markdown=f"# Report {i}",
            )
            report.save(temp_data_dir)
        
        reports = list_reports(temp_data_dir)
        assert len(reports) == 3


class TestDepthPresets:
    """Test research depth presets."""
    
    def test_depth_presets_exist(self):
        """Test that all depth presets are defined."""
        from gangdan.learning.research import DEPTH_PRESETS
        
        assert "quick" in DEPTH_PRESETS
        assert "medium" in DEPTH_PRESETS
        assert "deep" in DEPTH_PRESETS
        assert "auto" in DEPTH_PRESETS
        
        # Check structure
        for depth, (num_subtopics, rag_calls) in DEPTH_PRESETS.items():
            assert isinstance(num_subtopics, int)
            assert isinstance(rag_calls, int)
            assert num_subtopics > 0
            assert rag_calls > 0
    
    def test_output_size_presets_exist(self):
        """Test that output size presets are defined."""
        from gangdan.learning.research import OUTPUT_SIZE_PRESETS
        
        assert "short" in OUTPUT_SIZE_PRESETS
        assert "medium" in OUTPUT_SIZE_PRESETS
        assert "long" in OUTPUT_SIZE_PRESETS
        
        for size, config in OUTPUT_SIZE_PRESETS.items():
            assert "section_words" in config
            assert "notes_limit" in config
            assert "context_limit" in config


class TestEvaluateFindings:
    """Test research evaluation functions."""
    
    def test_evaluate_findings_sufficient(self, temp_data_dir):
        """Test evaluation when findings are sufficient."""
        from gangdan.learning.research import _evaluate_findings, ResearchSubtopic
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        subtopics = [
            ResearchSubtopic(
                title="Test 1",
                overview="Overview",
                notes="A" * 300,
                sources=["source1.md", "source2.md"]
            ),
            ResearchSubtopic(
                title="Test 2",
                overview="Overview",
                notes="B" * 300,
                sources=["source3.md"]
            ),
        ]
        
        result = _evaluate_findings(subtopics, "test topic", "en", ollama, config)
        
        assert result["sufficient"] == True
        assert result["weak_subtopics"] == []
    
    def test_jaccard_similarity(self):
        """Test Jaccard word similarity function."""
        from gangdan.learning.utils import jaccard_word_similarity
        
        # Identical texts
        sim1 = jaccard_word_similarity("hello world", "hello world")
        assert sim1 == 1.0
        
        # No overlap
        sim2 = jaccard_word_similarity("hello world", "foo bar")
        assert sim2 == 0.0
        
        # Partial overlap
        sim3 = jaccard_word_similarity("hello world test", "hello foo bar")
        assert 0 < sim3 < 1
        
        # Empty strings
        sim4 = jaccard_word_similarity("", "test")
        assert sim4 == 0.0


class TestResearchUtilities:
    """Test research utility functions."""
    
    def test_estimate_tokens(self):
        """Test token estimation."""
        from gangdan.learning.research import estimate_tokens
        
        text = "a" * 100
        tokens = estimate_tokens(text)
        assert tokens == 25  # 100 / 4
    
    def test_web_search_subtopic_mock(self):
        """Test web search subtopic (mocked)."""
        from gangdan.learning.research import _web_search_subtopic
        
        # Mock web searcher
        mock_searcher = Mock()
        mock_searcher.search.return_value = [
            {"title": "Result 1", "snippet": "Snippet 1", "url": "http://example.com"},
            {"title": "Result 2", "snippet": "Snippet 2", "url": "http://example.org"},
        ]
        
        context, results = _web_search_subtopic("Test Subtopic", "Test Topic", mock_searcher)
        
        assert len(context) > 0
        assert len(results) == 2
        assert "Result 1" in context


class TestJSONParsing:
    """Test JSON parsing utilities used by research module."""
    
    def test_parse_json_direct(self):
        """Test direct JSON parsing."""
        from gangdan.learning.utils import parse_json
        
        text = '{"key": "value"}'
        result = parse_json(text)
        assert result == {"key": "value"}
    
    def test_parse_json_with_markdown(self):
        """Test parsing JSON from markdown code blocks."""
        from gangdan.learning.utils import parse_json
        
        text = '```json\n{"key": "value"}\n```'
        result = parse_json(text)
        assert result == {"key": "value"}
    
    def test_parse_json_embedded(self):
        """Test parsing embedded JSON."""
        from gangdan.learning.utils import parse_json
        
        text = 'Some text before {"key": "value"} some text after'
        result = parse_json(text)
        assert result == {"key": "value"}


class TestLLMRetry:
    """Test LLM retry utilities."""
    
    def test_llm_call_with_retry_success(self):
        """Test successful LLM call."""
        from gangdan.learning.utils import llm_call_with_retry
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        result = llm_call_with_retry(
            ollama, config, [{"role": "user", "content": "test"}],
            temperature=0.7, max_retries=2, parse_json_response=False
        )
        
        assert result is not None
    
    def test_llm_stream_with_timeout(self):
        """Test LLM streaming with timeout."""
        from gangdan.learning.utils import llm_stream_with_timeout
        
        ollama = MockOllamaClient()
        config = MockConfig()
        
        chunks = list(llm_stream_with_timeout(
            ollama, config, [{"role": "user", "content": "test"}],
            temperature=0.7, timeout_seconds=30
        ))
        
        assert len(chunks) > 0


class TestValidation:
    """Test validation functions."""
    
    def test_validate_research_subtopics(self):
        """Test subtopic validation."""
        from gangdan.learning.utils import validate_research_subtopics
        
        valid_data = {
            "subtopics": [
                {"title": "Topic 1", "overview": "Overview 1"},
                {"title": "Topic 2", "overview": "Overview 2"},
            ]
        }
        is_valid, reason = validate_research_subtopics(valid_data, 2)
        assert is_valid
        
        invalid_data = {"subtopics": []}
        is_valid, reason = validate_research_subtopics(invalid_data, 2)
        assert not is_valid