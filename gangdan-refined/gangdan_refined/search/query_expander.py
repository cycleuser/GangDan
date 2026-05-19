"""LLM-assisted query expansion for academic search.

This module uses the configured LLM to analyze a simple keyword/query
and generate multiple optimized search queries across different strategies
(precise, broad, synonyms, preprint, GitHub).

The feature is opt-in: when disabled, the original query is returned as-is.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExpandedQuery:
    """Result of query expansion."""

    original: str
    expanded: List[str] = field(default_factory=list)
    precise: List[str] = field(default_factory=list)
    broad: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    preprint: List[str] = field(default_factory=list)
    github: List[str] = field(default_factory=list)
    dblp: List[str] = field(default_factory=list)
    domain: str = ""
    recommended_sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def all_queries(self) -> List[str]:
        """Return all expanded queries as a flat deduplicated list."""
        seen = set()
        result = []
        for q in self.expanded:
            q_lower = q.lower().strip()
            if q_lower and q_lower not in seen:
                seen.add(q_lower)
                result.append(q)
        return result


QUERY_EXPANSION_PROMPT = """You are an academic research search expert. Analyze the following research topic and generate optimized search queries.

Research topic: {query}

Generate search queries in these categories:
1. precise (2-3 queries): Exact searches targeting core concepts
2. broad (2-3 queries): Broader searches to expand scope
3. synonyms (2-3 queries): Using synonyms and related terminology
4. preprint (1-2 queries): Optimized for arXiv and preprint servers
5. github (1-2 queries): Optimized for GitHub code/repository search
6. dblp (1-2 queries): Optimized for DBLP computer science bibliography

Also identify:
- The research domain/field
- Recommended search sources from: arxiv, semantic_scholar, crossref, pubmed, github, openalex, dblp

Output ONLY a valid JSON object with this exact structure:
{{
    "domain": "field classification",
    "precise": ["query1", "query2"],
    "broad": ["query1", "query2"],
    "synonyms": ["query1", "query2"],
    "preprint": ["arXiv query"],
    "github": ["GitHub query"],
    "dblp": ["DBLP query"],
    "recommended_sources": ["arxiv", "semantic_scholar", "crossref", "openalex", "dblp"]
}}

Do not include any text before or after the JSON."""


class QueryExpander:
    """Expand search queries using LLM analysis.

    When query expansion is disabled, returns the original query unchanged.
    When enabled, calls the LLM to generate multiple optimized search strategies.

    Parameters
    ----------
    llm_client : Any
        LLM client with chat_complete(messages, model) method.
    enabled : bool
        Whether query expansion is active (default: False).
    model : str
        Model name to use for expansion. Empty string uses client default.
    """

    def __init__(
        self,
        llm_client: Any,
        enabled: bool = False,
        model: str = "",
    ) -> None:
        self.llm_client = llm_client
        self.enabled = enabled
        self.model = model

    def expand(self, query: str) -> ExpandedQuery:
        """Expand a search query into multiple optimized queries.

        Parameters
        ----------
        query : str
            Original search query/keyword.

        Returns
        -------
        ExpandedQuery
            Contains original query plus expanded variants grouped by strategy.
        """
        if not query.strip():
            return ExpandedQuery(original=query)

        if not self.enabled:
            return ExpandedQuery(
                original=query,
                expanded=[query],
                recommended_sources=["arxiv", "semantic_scholar", "crossref"],
            )

        logger.info("[QueryExpander] Expanding query: %s", query)

        try:
            response = self._call_llm(query)
            parsed = self._parse_response(response)
            result = self._build_expanded_query(query, parsed)
            logger.info(
                "[QueryExpander] Generated %d queries across %d categories",
                len(result.all_queries()),
                len([g for g in [result.precise, result.broad, result.synonyms, result.preprint, result.github] if g]),
            )
            return result
        except Exception as e:
            logger.error("[QueryExpander] Expansion failed, falling back: %s", e)
            return ExpandedQuery(
                original=query,
                expanded=[query],
                metadata={"fallback": True, "error": str(e)},
            )

    def _call_llm(self, query: str) -> str:
        """Call the LLM to expand the query.

        Parameters
        ----------
        query : str
            Original search query.

        Returns
        -------
        str
            Raw LLM response text.
        """
        prompt = QUERY_EXPANSION_PROMPT.format(query=query)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an academic research search expert. "
                    "Always respond with valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        kwargs: Dict[str, Any] = {"messages": messages}
        if self.model:
            kwargs["model"] = self.model

        response = self.llm_client.chat_complete(**kwargs)

        if not response or "[Error" in response:
            raise ValueError(f"LLM returned error response: {response}")

        return response

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM JSON response.

        Parameters
        ----------
        response : str
            Raw LLM response text.

        Returns
        -------
        Dict[str, Any]
            Parsed JSON data.

        Raises
        ------
        ValueError
            If response cannot be parsed as valid JSON.
        """
        text = response.strip()

        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            raise ValueError("No JSON object found in response")

        json_str = json_match.group(0)
        data = json.loads(json_str)

        required_keys = [
            "domain",
            "precise",
            "broad",
            "synonyms",
            "preprint",
            "github",
            "recommended_sources",
        ]
        for key in required_keys:
            if key not in data:
                data[key] = [] if key != "domain" else ""

        return data

    def _build_expanded_query(self, original: str, data: Dict[str, Any]) -> ExpandedQuery:
        """Build ExpandedQuery from parsed LLM data.

        Parameters
        ----------
        original : str
            Original query string.
        data : Dict[str, Any]
            Parsed LLM response data.

        Returns
        -------
        ExpandedQuery
            Structured expansion result.
        """
        precise = [q.strip() for q in data.get("precise", []) if q.strip()]
        broad = [q.strip() for q in data.get("broad", []) if q.strip()]
        synonyms = [q.strip() for q in data.get("synonyms", []) if q.strip()]
        preprint = [q.strip() for q in data.get("preprint", []) if q.strip()]
        github = [q.strip() for q in data.get("github", []) if q.strip()]
        dblp = [q.strip() for q in data.get("dblp", []) if q.strip()]

        all_expanded = precise + broad + synonyms + preprint + github + dblp
        if not all_expanded:
            all_expanded = [original]

        sources = data.get("recommended_sources", [])
        valid_sources = [
            s for s in sources
            if s in ("arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp")
        ]
        if not valid_sources:
            valid_sources = ["arxiv", "semantic_scholar", "crossref"]

        return ExpandedQuery(
            original=original,
            expanded=all_expanded,
            precise=precise,
            broad=broad,
            synonyms=synonyms,
            preprint=preprint,
            github=github,
            dblp=dblp,
            domain=data.get("domain", ""),
            recommended_sources=valid_sources,
        )
