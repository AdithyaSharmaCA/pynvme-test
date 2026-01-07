"""
OCP 2.0 Specification Parser
Flat SHALL Records (No Nested Requirements)
LLM-Ready, Lossless, Deterministic
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import fitz
import pdfplumber


# =========================
# Data Models
# =========================

@dataclass
class HierarchyTree:
    parent: Optional[str]
    grandparent: Optional[str]
    ancestors: List[str]


@dataclass
class SectionMetadata:
    content_length: int
    requirement_count: int
    reference_count: int
    has_subsections: bool
    depth: int
    word_count_in_section: int


# =========================
# Parser
# =========================

class OCPSpecificationParser:

    SECTION_PATTERN = re.compile(r'^(\d+(?:\.\d+)*)(\s+)(.+)$')
    SHALL_PATTERN = re.compile(r'\bshall\b', re.IGNORECASE)
    ANCHOR_PATTERN = re.compile(r'\(see\b[^)]*\)', re.IGNORECASE)

    KEY_PHRASE_PATTERNS = [
        r'\bshall not\b',
        r'\bshall\b',
        r'\bmust\b',
        r'\b\d+\s*(ms|us|ns|s|V|A|W|%)\b',
        r'\b0x[0-9A-Fa-f]+\b',
        r'\b(enable|disable|supported|unsupported)\b',
        r'\b[A-Z][A-Za-z0-9_]+\b'
    ]

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        self.section_title_map: Dict[str, str] = {}

    # =========================
    # PDF Extraction
    # =========================

    def extract_text_with_pages(self) -> List[Dict[str, Any]]:
        pages = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text:
                        pages.append({"page_number": i, "text": text})
        except Exception:
            doc = fitz.open(self.pdf_path)
            for i in range(len(doc)):
                pages.append({"page_number": i + 1, "text": doc[i].get_text()})
            doc.close()
        return pages

    # =========================
    # Hierarchy
    # =========================

    def build_hierarchy_tree(self, section_number: str) -> HierarchyTree:
        parts = section_number.split(".")
        ancestors = []
        for i in range(1, len(parts)):
            key = ".".join(parts[:i])
            if key in self.section_title_map:
                ancestors.append(self.section_title_map[key])
        return HierarchyTree(
            parent=ancestors[-1] if ancestors else None,
            grandparent=ancestors[-2] if len(ancestors) > 1 else None,
            ancestors=ancestors
        )

    # =========================
    # Key Phrases
    # =========================

    def extract_key_phrases(self, text: str) -> List[str]:
        phrases = set()
        for pattern in self.KEY_PHRASE_PATTERNS:
            for match in re.findall(pattern, text, re.IGNORECASE):
                phrases.add(match if isinstance(match, str) else match[0])
        return sorted(phrases)

    # =========================
    # Parsing
    # =========================

    def parse(self) -> List[Dict[str, Any]]:
        pages = self.extract_text_with_pages()
        output = []
        current = None

        for page in pages:
            lines = page["text"].splitlines()
            for idx, line in enumerate(lines):

                match = self.SECTION_PATTERN.match(line)
                if match:
                    if current:
                        output.extend(self._finalize_section(current))

                    number = match.group(1)
                    title = match.group(3)
                    full_name = f"{number} {title}"
                    self.section_title_map[number] = full_name

                    current = {
                        "number": number,
                        "hierarchy": full_name,
                        "page_number": page["page_number"],
                        "lines": []
                    }
                elif current:
                    current["lines"].append(line)

        if current:
            output.extend(self._finalize_section(current))

        return output

    # =========================
    # Finalization
    # =========================

    def _finalize_section(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        lines = data["lines"]
        content = "\n".join(lines)
        hierarchy_tree = self.build_hierarchy_tree(data["number"])

        metadata = SectionMetadata(
            content_length=len(content),
            requirement_count=0,
            reference_count=len(self.ANCHOR_PATTERN.findall(content)),
            has_subsections="." in data["number"],
            depth=len(data["number"].split(".")),
            word_count_in_section=len(content.split())
        )

        records = []

        for idx, line in enumerate(lines):
            if not self.SHALL_PATTERN.search(line):
                continue

            before = next((lines[i] for i in range(idx - 1, -1, -1) if lines[i].strip()), None)
            after = next((lines[i] for i in range(idx + 1, len(lines)) if lines[i].strip()), None)

            anchor_match = self.ANCHOR_PATTERN.search(line)
            if not anchor_match and after:
                anchor_match = self.ANCHOR_PATTERN.search(after)

            records.append({
                "hierarchy": data["hierarchy"],
                "hierarchy_tree": hierarchy_tree.__dict__,
                "page_number": data["page_number"],
                "shall_sentence": line.strip(),
                "before_shall": before,
                "after_shall": after,
                "anchor": anchor_match.group(0) if anchor_match else None,
                "key_phrases": self.extract_key_phrases(line),
                "metadata": metadata.__dict__
            })

        # section with NO shall → still emit once
        if not records:
            records.append({
                "hierarchy": data["hierarchy"],
                "hierarchy_tree": hierarchy_tree.__dict__,
                "page_number": data["page_number"],
                "shall_sentence": None,
                "before_shall": None,
                "after_shall": None,
                "anchor": None,
                "key_phrases": [],
                "metadata": metadata.__dict__
            })

        metadata.requirement_count = len(records)
        return records

    # =========================
    # JSON Output
    # =========================

    def to_json(self, output_path: str):
        Path(output_path).write_text(
            json.dumps(self.parse(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


# =========================
# CLI
# =========================

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ocp_parser.py <ocp_pdf> [output.json]")
        return

    parser = OCPSpecificationParser(sys.argv[1])
    output = sys.argv[2] if len(sys.argv) > 2 else "ocp_flat_shalls.json"
    parser.to_json(output)
    print(f"Output written to {output}")


if __name__ == "__main__":
    main()
