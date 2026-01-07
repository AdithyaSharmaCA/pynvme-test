"""
OCP 2.0 Specification Parser (Lossless Version)

Preserves all strings exactly as they appear in the OCP PDF.
- Section titles unchanged
- Formatting unchanged
- Anchors extracted ONLY from explicit "see <Section name>"
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import fitz  # PyMuPDF
import pdfplumber


# =========================
# Data Models
# =========================

@dataclass
class HierarchyTree:
    current: str
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
    word_count: int


@dataclass
class Section:
    id: str
    hierarchy: str
    title: str
    hierarchy_tree: HierarchyTree
    anchors: List[str]
    shall_sentences: List[str]
    page_number: int
    key_phrases: List[str]
    metadata: SectionMetadata
    raw_content: str


# =========================
# Parser
# =========================

class OCPSpecificationParser:
    """
    Lossless OCP Specification Parser
    """

    # SECTION HEADER (NON-DESTRUCTIVE)
    # Example: 3.2.1 Power Distribution Requirements
    SECTION_PATTERN = re.compile(
        r'^(\d+(?:\.\d+)*)(\s+)(.+)$',
        re.MULTILINE
    )

    # SHALL detection (line-based, lossless)
    SHALL_PATTERN = re.compile(r'\bshall\b', re.IGNORECASE)

    # ONLY explicit anchors: "see <Section name>"
    ANCHOR_PATTERN = re.compile(
        r'\bsee\s+[^\n.,;]+',
        re.IGNORECASE
    )

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # =========================
    # PDF Extraction
    # =========================

    def extract_text_with_pages(self) -> List[Dict[str, Any]]:
        pages_data = []

        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text:
                        pages_data.append({
                            "page_number": page_num,
                            "text": text,
                            "method": "pdfplumber"
                        })
        except Exception:
            doc = fitz.open(self.pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                pages_data.append({
                    "page_number": page_num + 1,
                    "text": page.get_text(),
                    "method": "pymupdf"
                })
            doc.close()

        return pages_data

    # =========================
    # Hierarchy
    # =========================

    def build_hierarchy_tree(self, hierarchy: str) -> HierarchyTree:
        parts = hierarchy.split(".")
        ancestors = [".".join(parts[:i + 1]) for i in range(len(parts) - 1)]

        return HierarchyTree(
            current=hierarchy,
            parent=".".join(parts[:-1]) if len(parts) > 1 else None,
            grandparent=".".join(parts[:-2]) if len(parts) > 2 else None,
            ancestors=ancestors
        )

    # =========================
    # Extraction (Lossless)
    # =========================

    def extract_anchors(self, text: str) -> List[str]:
        return [m.group(0) for m in self.ANCHOR_PATTERN.finditer(text)]

    def extract_shall_sentences(self, text: str) -> List[str]:
        results = []
        for line in text.splitlines():
            if self.SHALL_PATTERN.search(line):
                results.append(line)
        return results

    # Key phrases intentionally disabled to avoid mutation
    def extract_key_phrases(self, text: str) -> List[str]:
        return []

    # =========================
    # Section Parsing
    # =========================

    def parse_sections(self, pages_data: List[Dict[str, Any]]) -> List[Section]:
        sections = []
        current_section = None

        for page_data in pages_data:
            page_number = page_data["page_number"]
            lines = page_data["text"].splitlines()

            for line in lines:
                match = self.SECTION_PATTERN.match(line)

                if match:
                    if current_section:
                        sections.append(self._finalize_section(current_section))

                    current_section = {
                        "hierarchy": match.group(1),
                        "title": match.group(3),  # EXACT title
                        "page_number": page_number,
                        "content": "",
                    }
                elif current_section:
                    current_section["content"] += line + "\n"

        if current_section:
            sections.append(self._finalize_section(current_section))

        return sections

    # =========================
    # Finalization
    # =========================

    def _finalize_section(self, section_data: Dict) -> Section:
        content = section_data["content"]

        hierarchy_tree = self.build_hierarchy_tree(section_data["hierarchy"])
        anchors = self.extract_anchors(content)
        shall_sentences = self.extract_shall_sentences(content)
        key_phrases = []

        metadata = SectionMetadata(
            content_length=len(content),
            requirement_count=len(shall_sentences),
            reference_count=len(anchors),
            has_subsections="." in section_data["hierarchy"],
            depth=len(section_data["hierarchy"].split(".")),
            word_count=len(content.split())
        )

        return Section(
            id=f'section_{section_data["hierarchy"].replace(".", "_")}',
            hierarchy=section_data["hierarchy"],
            title=section_data["title"],
            hierarchy_tree=hierarchy_tree,
            anchors=anchors,
            shall_sentences=shall_sentences,
            page_number=section_data["page_number"],
            key_phrases=key_phrases,
            metadata=metadata,
            raw_content=content  # FULL, UNTRUNCATED
        )

    # =========================
    # Public APIs
    # =========================

    def parse(self) -> List[Section]:
        pages = self.extract_text_with_pages()
        return self.parse_sections(pages)

    def to_json(self, sections: List[Section], output_path: Optional[str] = None) -> str:
        data = []

        for s in sections:
            data.append({
                "id": s.id,
                "hierarchy": s.hierarchy,
                "title": s.title,
                "hierarchyTree": {
                    "current": s.hierarchy_tree.current,
                    "parent": s.hierarchy_tree.parent,
                    "grandparent": s.hierarchy_tree.grandparent,
                    "ancestors": s.hierarchy_tree.ancestors,
                },
                "anchors": s.anchors,
                "shallSentences": s.shall_sentences,
                "pageNumber": s.page_number,
                "keyPhrases": s.key_phrases,
                "metadata": {
                    "contentLength": s.metadata.content_length,
                    "requirementCount": s.metadata.requirement_count,
                    "referenceCount": s.metadata.reference_count,
                    "hasSubsections": s.metadata.has_subsections,
                    "depth": s.metadata.depth,
                    "wordCount": s.metadata.word_count,
                },
                "rawContent": s.raw_content,
            })

        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        if output_path:
            Path(output_path).write_text(json_str, encoding="utf-8")

        return json_str

    def generate_statistics(self, sections: List[Section]) -> Dict[str, Any]:
        return {
            "total_sections": len(sections),
            "total_requirements": sum(len(s.shall_sentences) for s in sections),
            "total_references": sum(len(s.anchors) for s in sections),
            "max_hierarchy_depth": max((s.metadata.depth for s in sections), default=0),
            "total_words": sum(s.metadata.word_count for s in sections),
        }


# =========================
# CLI
# =========================

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ocp_parser.py <ocp_pdf> [output.json]")
        sys.exit(1)

    parser = OCPSpecificationParser(sys.argv[1])
    sections = parser.parse()
    output = sys.argv[2] if len(sys.argv) > 2 else "ocp_parsed_output.json"
    parser.to_json(sections, output)

    print(f"Parsed {len(sections)} sections")
    print(f"Output written to {output}")


if __name__ == "__main__":
    main()
