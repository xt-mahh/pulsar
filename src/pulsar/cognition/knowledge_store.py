"""KnowledgeStore — reads Markdown files with YAML frontmatter.

Provides platform rules, style templates, and search over the knowledge base.
Phase 1: file-system reading. Phase 2: vector/semantic search.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Knowledge store access layer.

    Reads Markdown/YAML knowledge files from a base directory.
    Each Markdown file should have YAML frontmatter delimited by '---'.
    Pure YAML files are also supported for style templates.

    Phase 1: Direct file read.
    Phase 2: Vector/semantic retrieval.
    """

    def __init__(self, base_path: str = "cognition/knowledge"):
        self.base_path = Path(base_path)

    # ── Public API ──────────────────────────────────────────────────

    async def get_platform_rules(self, platform: str) -> dict:
        """Get the publishing rules for a specific platform.

        Reads: <base_path>/<platform>/rules.md

        Args:
            platform: Platform identifier (e.g. "wechat", "xiaohongshu").

        Returns:
            Dict parsed from the YAML frontmatter or empty dict.
        """
        path = self.base_path / platform / "rules.md"
        return await self._read_yaml_frontmatter(path)

    async def get_platform_limits(self, platform: str) -> dict:
        """Get API frequency and quota limits for a platform.

        Reads: <base_path>/<platform>/limits.md
        """
        path = self.base_path / platform / "limits.md"
        return await self._read_yaml_frontmatter(path)

    async def get_tips(self, platform: str) -> list[str]:
        """Get best-practice tips for a platform.

        Reads: <base_path>/<platform>/tips.md

        Returns:
            List of tip strings (non-empty lines from the body).
        """
        path = self.base_path / platform / "tips.md"
        raw = await self._read_markdown_body(path)
        return [line.strip() for line in raw.split("\n") if line.strip()]

    async def get_style(self, style_name: str) -> Optional[dict]:
        """Get a writing style template configuration.

        Reads: <base_path>/templates/<style_name>.yaml

        Args:
            style_name: Style name (e.g. "科普", "专业", "技术").

        Returns:
            Dict from YAML or None if not found.
        """
        path = self.base_path / "templates" / f"{style_name}.yaml"
        return await self._read_yaml_file(path)

    async def search(self, query: str, tags: list[str] | None = None) -> list[dict]:
        """Search knowledge entries by keyword/tag matching.

        Phase 1: Simple filename + tag matching.
        Phase 2: Vector semantic search.

        Args:
            query: Search query string.
            tags: Optional list of tags to filter by.

        Returns:
            List of matching entries with path and metadata.
        """
        results: list[dict] = []
        query_lower = query.lower()

        for md_path in sorted(self.base_path.rglob("*.md")):
            frontmatter = await self._read_yaml_frontmatter(md_path)
            file_tags = frontmatter.get("tags", [])

            # Filter by tags if specified
            if tags and not any(t in file_tags for t in tags):
                continue

            # Simple keyword match on filename or tags
            path_str = str(md_path.relative_to(self.base_path)).lower()
            if query_lower in path_str or any(query_lower in t.lower() for t in file_tags):
                results.append({
                    "path": str(md_path.relative_to(self.base_path)),
                    "metadata": frontmatter,
                })

        return results

    async def get_all_documents(self) -> list[dict]:
        """List all knowledge documents (Phase 1: files only)."""
        results = []
        for md_path in sorted(self.base_path.rglob("*.md")):
            frontmatter = await self._read_yaml_frontmatter(md_path)
            results.append({
                "path": str(md_path.relative_to(self.base_path)),
                "metadata": frontmatter,
            })
        for yaml_path in sorted(self.base_path.rglob("*.yaml")):
            # Skip files inside templates/ that start with known patterns
            data = await self._read_yaml_file(yaml_path)
            if data:
                results.append({
                    "path": str(yaml_path.relative_to(self.base_path)),
                    "metadata": data,
                })
        return results

    # ── Internal readers ────────────────────────────────────────────

    async def _read_yaml_frontmatter(self, path: Path) -> dict:
        """Read the YAML frontmatter from a Markdown file.

        Format:
            ---
            key: value
            ---
            Body text...

        Returns:
            Parsed YAML dict, or empty dict if parsing fails.
        """
        try:
            import yaml
            loop = asyncio.get_event_loop()

            def _read():
                if not path.exists():
                    return {}
                content = path.read_text(encoding="utf-8")
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    return yaml.safe_load(parts[1]) or {}
                return {}

            return await loop.run_in_executor(None, _read)
        except ImportError:
            logger.warning("PyYAML not installed; frontmatter parsing disabled")
            return {}
        except Exception as e:
            logger.warning("Failed to read frontmatter from %s: %s", path, e)
            return {}

    async def _read_yaml_file(self, path: Path) -> Optional[dict]:
        """Read a pure YAML file.

        Returns:
            Parsed YAML dict, or None if file doesn't exist or parsing fails.
        """
        try:
            import yaml
            loop = asyncio.get_event_loop()

            def _read():
                if not path.exists():
                    return None
                return yaml.safe_load(path.read_text(encoding="utf-8"))

            return await loop.run_in_executor(None, _read)
        except ImportError:
            logger.warning("PyYAML not installed; YAML reading disabled")
            return None
        except Exception as e:
            logger.warning("Failed to read YAML file %s: %s", path, e)
            return None

    async def _read_markdown_body(self, path: Path) -> str:
        """Read the Markdown body (stripping YAML frontmatter)."""
        try:
            loop = asyncio.get_event_loop()

            def _read():
                if not path.exists():
                    return ""
                content = path.read_text(encoding="utf-8")
                parts = content.split("---", 2)
                return parts[2].strip() if len(parts) >= 3 else content.strip()

            return await loop.run_in_executor(None, _read)
        except Exception as e:
            logger.warning("Failed to read markdown body from %s: %s", path, e)
            return ""


