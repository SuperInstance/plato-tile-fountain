"""Tile fountain — auto-generate tiles from structured content."""

import re
from typing import Optional

class TileFountain:
    def generate_from_text(self, text: str, domain: str = "text", confidence: float = 0.5) -> list[dict]:
        tiles = []
        for sent in text.split("."):
            sent = sent.strip()
            if 10 <= len(sent) <= 1000:
                tiles.append({"content": sent, "domain": domain, "confidence": confidence})
        return tiles

    def generate_from_headings(self, text: str, confidence: float = 0.6) -> list[dict]:
        tiles = []
        for m in re.finditer(r"^#+\s+(.+)$", text, re.MULTILINE):
            tiles.append({"content": m.group(1), "domain": "heading", "confidence": confidence})
        return tiles

    def generate_from_code(self, code: str, language: str = "python", confidence: float = 0.7) -> list[dict]:
        tiles = []
        for m in re.finditer(r'""".*?"""', code, re.DOTALL):
            doc = m.group(0).strip('"').strip()
            if len(doc) > 10:
                tiles.append({"content": doc, "domain": f"code-{language}", "confidence": confidence})
        for m in re.finditer(r"#\s*(.+)$", code, re.MULTILINE):
            comment = m.group(1).strip()
            if len(comment) > 15:
                tiles.append({"content": comment, "domain": f"code-{language}", "confidence": confidence * 0.8})
        return tiles

    def generate_from_faq(self, faq_pairs: list[tuple[str, str]], domain: str = "faq") -> list[dict]:
        tiles = []
        for q, a in faq_pairs:
            tiles.append({"content": f"Q: {q}\nA: {a}", "domain": domain, "confidence": 0.8})
        return tiles

    def generate_from_definitions(self, definitions: list[tuple[str, str]], domain: str = "glossary") -> list[dict]:
        tiles = []
        for term, defn in definitions:
            tiles.append({"content": f"{term}: {defn}", "domain": domain, "confidence": 0.9})
        return tiles

    def generate_from_model_output(self, model_text: str, domain: str = "ml-output", confidence: float = 0.6) -> list[dict]:
        tiles = []
        for chunk in model_text.split("\n\n"):
            chunk = chunk.strip()
            if 20 <= len(chunk) <= 500:
                tiles.append({"content": chunk, "domain": domain, "confidence": confidence})
        return tiles

    @property
    def stats(self) -> dict:
        return {"generators": 6, "zero_external_deps": True}
