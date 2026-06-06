"""Skill loader for GangDan.

Scans `.reasonix/skills/` directories for skill playbooks defined as
SKILL.md files. Skills can be invoked inline (body folded into the
current turn) or as extensions to the learning/research pipeline.

Design inspired by nanobot's skill system and DeepSeek-Reasonix's
skill/ directory conventions.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Standard directory name for skills within a project
SKILLS_DIRNAME = "skills"

# Canonical skill filename
SKILL_FILE = "SKILL.md"

# YAML-style frontmatter pattern
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Skill:
    """A loaded skill playbook.

    Attributes
    ----------
    name : str
        Canonical identifier (derived from directory/filename).
    description : str
        One-liner describing what the skill does.
    body : str
        Full markdown body (instructions for the agent).
    path : str
        Absolute path to the SKILL.md file, or "(builtin)".
    scope : str
        "project", "global", or "builtin".
    """

    name: str
    description: str = ""
    body: str = ""
    path: str = ""
    scope: str = "project"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for API responses."""
        return {
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "path": self.path,
        }


# ---------------------------------------------------------------------------
# Built-in skills
# ---------------------------------------------------------------------------

_BUILTIN_SKILLS: Dict[str, Skill] = {}


def _register_builtin(name: str, description: str, body: str) -> None:
    _BUILTIN_SKILLS[name] = Skill(
        name=name,
        description=description,
        body=body,
        path="(builtin)",
        scope="builtin",
    )


# Summarize documents
_register_builtin(
    "summarize",
    "Summarize one or more documents from the knowledge base into a concise overview.",
    """You are a document summarizer. When invoked:

1. Identify the key documents from the user's knowledge base
2. Extract the main thesis, methodology, and findings from each
3. Produce a structured summary with:
   - Title and authors (if available)
   - Main argument / thesis
   - Key methods used
   - Primary findings
   - Relevance to the user's research interest
4. Keep each document summary under 200 words
5. End with a cross-document synthesis highlighting common themes and contradictions""",
)

# Compare documents
_register_builtin(
    "compare",
    "Compare two or more documents, highlighting similarities and differences.",
    """You are a document comparison specialist. When invoked:

1. Identify the documents to compare from the knowledge base
2. For each document, extract:
   - Core thesis / research question
   - Methodology
   - Key findings
   - Assumptions and limitations
3. Build a comparison table covering these dimensions
4. Highlight:
   - Where the documents agree
   - Where they disagree or diverge
   - Complementary insights
5. Suggest which document is more applicable to different contexts""",
)

# Extract methodology
_register_builtin(
    "extract_methods",
    "Extract and categorize research methodologies from documents in the knowledge base.",
    """You are a methodology analyst. When invoked:

1. Scan the knowledge base for descriptions of research methods
2. For each method found, extract:
   - Method name and category (experimental, theoretical, computational, survey, etc.)
   - Data requirements
   - Key parameters and configurations
   - Evaluation metrics used
   - Limitations noted by the authors
3. Organize findings by methodology category
4. Note any novel or hybrid methods
5. Suggest which methods are most reproducible based on the documentation""",
)

# Literature review generator
_register_builtin(
    "literature_review",
    "Generate a structured literature review from knowledge base documents on a given topic.",
    """You are a literature review assistant. When invoked:

1. Survey all relevant documents in the knowledge base on the given topic
2. Organize the review as follows:
   ## Historical Context
   Key developments and seminal works
   
   ## Current State of the Art
   Recent advances and active research directions
   
   ## Methodological Landscape
   Common approaches and their trade-offs
   
   ## Open Problems
   Unresolved questions and limitations
   
   ## Future Directions
   Promising avenues for further research
3. Cite specific documents using [Author (Year)] format
4. Be balanced: acknowledge conflicting findings and debates
5. End with a summary table of key papers and their contributions""",
)


class SkillLoader:
    """Discovers and loads skills from disk.

    Scans project-level `.reasonix/skills/` and global `~/.gangdan/skills/`.
    Project skills take precedence over global skills on name collision.

    Attributes
    ----------
    project_root : Path
        Root directory of the project to scan.
    user_dir : Path or None
        User's global config directory for skills.
    """

    def __init__(
        self,
        project_root: str,  # Path also accepted
        user_dir: Optional[str] = None,  # Path also accepted
    ) -> None:
        """Initialize skill loader.

        Parameters
        ----------
        project_root : str or Path
            Project root directory.
        user_dir : str or Path, optional
            User's global config directory (e.g., ~/.gangdan).
        """
        self.project_root = Path(project_root)
        self.user_dir = Path(user_dir) if user_dir else None
        self._skills: Optional[Dict[str, Skill]] = None

    def load_all(self) -> Dict[str, Skill]:
        """Load all available skills.

        Scopes in priority order: builtin < global < project.

        Returns
        -------
        Dict[str, Skill]
            Skills keyed by name.
        """
        if self._skills is not None:
            return self._skills

        skills: Dict[str, Skill] = {}

        # Builtins (lowest priority)
        for name, skill in _BUILTIN_SKILLS.items():
            skills[name] = skill

        # Global skills
        if self.user_dir:
            global_skills_dir = self.user_dir / SKILLS_DIRNAME
            if global_skills_dir.exists():
                for sk in self._load_from_dir(global_skills_dir, "global"):
                    skills[sk.name] = sk

        # Project skills (highest priority)
        convention_dirs = [
            self.project_root / ".reasonix",
            self.project_root / ".agents",
            self.project_root / ".agent",
            self.project_root / ".claude",
        ]
        for conv_dir in convention_dirs:
            skills_dir = conv_dir / SKILLS_DIRNAME
            if skills_dir.exists():
                for sk in self._load_from_dir(skills_dir, "project"):
                    skills[sk.name] = sk

        self._skills = skills
        logger.info(
            "Skills: loaded %d skills (builtin=%d, project=%d, global=%d)",
            len(skills),
            sum(1 for s in skills.values() if s.scope == "builtin"),
            sum(1 for s in skills.values() if s.scope == "project"),
            sum(1 for s in skills.values() if s.scope == "global"),
        )
        return skills

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Parameters
        ----------
        name : str
            Skill name (case-sensitive).

        Returns
        -------
        Skill or None
            The skill, or None if not found.
        """
        skills = self.load_all()
        return skills.get(name)

    def list_skills(self) -> List[Skill]:
        """List all available skills.

        Returns
        -------
        List[Skill]
            All loaded skills sorted by name.
        """
        skills = self.load_all()
        return sorted(skills.values(), key=lambda s: s.name)

    def _load_from_dir(self, directory: Path, scope: str) -> List[Skill]:
        """Load skills from a directory.

        Supports two layouts:
        1. Directory layout: `<name>/SKILL.md`
        2. Flat layout: `<name>.md`

        Parameters
        ----------
        directory : Path
            Directory to scan.
        scope : str
            Skill scope label ("project" or "global").

        Returns
        -------
        List[Skill]
            Loaded skills.
        """
        skills: List[Skill] = []
        if not directory.exists():
            return skills

        # Directory layout: <name>/SKILL.md
        for subdir in sorted(directory.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("."):
                skill_file = subdir / SKILL_FILE
                if skill_file.exists():
                    skill = self._parse_skill_file(skill_file, subdir.name, scope)
                    if skill:
                        skills.append(skill)

        # Flat layout: <name>.md
        for md_file in sorted(directory.glob("*.md")):
            if md_file.name.upper() == SKILL_FILE:
                continue  # Skip SKILL.md files already handled
            name = md_file.stem
            skill = self._parse_skill_file(md_file, name, scope)
            if skill:
                skills.append(skill)

        return skills

    def _parse_skill_file(self, filepath: Path, name: str, scope: str) -> Optional[Skill]:
        """Parse a SKILL.md file into a Skill object.

        Expected format:
        ```
        ---
        description: One-line description
        ---
        Body content (instructions for the agent)...
        ```

        Parameters
        ----------
        filepath : Path
            Path to the skill file.
        name : str
            Skill name.
        scope : str
            Skill scope.

        Returns
        -------
        Skill or None
            Parsed skill, or None on error.
        """
        try:
            content = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skills: failed to read %s: %s", filepath, e)
            return None

        description = ""
        body = content

        # Parse YAML frontmatter (simple key: value parsing)
        match = _FRONTMATTER_RE.match(content)
        if match:
            frontmatter = match.group(1)
            body = content[match.end():].strip()
            for line in frontmatter.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    if key.strip() == "description":
                        description = val.strip().strip('"').strip("'")

        # If no frontmatter description, use first non-empty line
        if not description:
            for line in body.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped[:120]
                    break

        return Skill(
            name=name,
            description=description,
            body=body,
            path=str(filepath),
            scope=scope,
        )


# ---------------------------------------------------------------------------
# Convenience: invoke a skill (builds a system-prompt snippet)
# ---------------------------------------------------------------------------

def build_skill_prompt(skill: Skill) -> str:
    """Build a prompt snippet for invoking a skill inline.

    Parameters
    ----------
    skill : Skill
        The skill to invoke.

    Returns
    -------
    str
        A system-prompt-style instruction block.
    """
    return (
        f"<!-- SKILL: {skill.name} -->\n"
        f"{skill.body}\n"
        f"<!-- END SKILL: {skill.name} -->"
    )
