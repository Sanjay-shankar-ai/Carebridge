"""
CareBridge Reviewed Knowledge Retrieval Service (AI Behaviour B6)
Retrieves grounded clinical and navigation knowledge strictly from files with:
  - reviewed: true
  - matching role (patient, doctor, care_coordinator)
  - matching language (en, es, ar)
Never returns unreviewed, wrong-role, or wrong-language content.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


def _strip_yaml_value(raw_val: str) -> Any:
    """Strips inline YAML comments (outside quotes), unquotes strings, and parses booleans."""
    s = raw_val.strip()
    if len(s) >= 2 and s[0] in ('"', "'") and s[0] in s[1:]:
        quote = s[0]
        end_idx = s.find(quote, 1)
        return s[1:end_idx]
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    return s


def _parse_frontmatter(raw: str) -> Tuple[Dict[str, Any], str]:
    """Parses simple YAML frontmatter delimited by --- lines (supports inline # comments and audience/role)."""
    text = raw.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    meta: Dict[str, Any] = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = _strip_yaml_value(v)
    return meta, parts[2].strip()


def _normalize_role(role: str) -> str:
    r = (role or "").lower().strip()
    if r in ("clinician", "specialist"):
        return "doctor"
    if r == "coordinator":
        return "care_coordinator"
    return r


def _tokens(text: str) -> set:
    return set(re.findall(r"[\w\u0600-\u06ff]+", (text or "").lower()))


class KnowledgeRetrievalService:
    """Strictly filtered knowledge retriever (`reviewed: true` + matching role + language)."""

    @classmethod
    def load_all(cls, knowledge_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        base = Path(knowledge_dir) if knowledge_dir else DEFAULT_KNOWLEDGE_DIR
        if not base.exists():
            return []
        docs: List[Dict[str, Any]] = []
        for path in sorted(base.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            docs.append({
                "id": str(meta.get("id") or path.stem),
                "path": str(path),
                "title": str(meta.get("title") or meta.get("id") or path.stem),
                "type": str(meta.get("type", "")).lower().strip(),
                "role": _normalize_role(str(meta.get("audience") or meta.get("role") or "")),
                "audience": _normalize_role(str(meta.get("audience") or meta.get("role") or "")),
                "language": str(meta.get("language", "")).lower().strip(),
                "topic": str(meta.get("topic", "")).lower().strip(),
                "owner": str(meta.get("owner", "")).strip(),
                "reviewed": meta.get("reviewed") is True,
                "body": body,
            })
        return docs

    @classmethod
    def retrieve(
        cls,
        query: str,
        *,
        role: str,
        language: str = "en",
        limit: int = 3,
        knowledge_dir: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns up to `limit` reviewed documents matching `role` and `language`,
        ranked by token overlap with `query`.
        """
        norm_role = _normalize_role(role)
        norm_lang = (language or "en").lower().strip()
        q_tokens = _tokens(query)

        candidates = [
            d for d in cls.load_all(knowledge_dir)
            if d["reviewed"] is True and d["role"] == norm_role and d["language"] == norm_lang
        ]

        scored = []
        for doc in candidates:
            haystack = _tokens(f"{doc['title']} {doc['topic']} {doc['body']}")
            overlap = len(q_tokens & haystack) if q_tokens else 1
            scored.append((overlap, doc))

        scored.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [doc for score, doc in scored[:limit] if score > 0 or not q_tokens]
