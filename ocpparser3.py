"""
OCP 2.0 Specification Parser (Lossless + Named Hierarchy)

- Preserves all text verbatim
- Hierarchy includes section number + section name
- Hierarchy tree contains named parent / ancestors
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
    hierarchy_tree: HierarchyTree
    title: str
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
    Lossless OCP Specification Parser with Named Hierarchy
    """

    # Section header (lossless)
    SECTION_PATTERN = re.compile(
        r'^(\d+(?:\.\d+)*)(\s+)(.+)$',
        re.MULTILINE
    )

    SHALL_PATTERN = re.compile(r'\bshall\b', re.IGNORECASE)

    # ONLY explicit anchors
    ANCHOR_PATTERN = re.compile(
        r'\bsee\s+[^\n.,;]+',
        re.IGNORECASE
    )

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # section_number -> "3.2 Power Distribution"
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
                        pages.append({
                            "page_number": i,
                            "text": text
                        })
        except Exception:
            doc = fitz.open(self.pdf_path)
            for i in range(len(doc)):
                pages.append({
                    "page_number": i + 1,
                    "text": doc[i].get_text()
                })
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

        current = self.section_title_map.get(section_number, section_number)
        parent = ancestors[-1] if ancestors else None
        grandparent = ancestors[-2] if len(ancestors) >= 2 else None

        return HierarchyTree(
            current=current,
            parent=parent,
            grandparent=grandparent,
            ancestors=ancestors
        )

    # =========================
    # Extraction (Lossless)
    # =========================

    def extract_anchors(self, text: str) -> List[str]:
        return [m.group(0) for m in self.ANCHOR_PATTERN.finditer(text)]

    def extract_shall_sentences(self, text: str) -> List[str]:
        return [line for line in text.splitlines() if self.SHALL_PATTERN.search(line)]

    def extract_key_phrases(self, text: str) -> List[str]:
        return []  # disabled for lossless parsing

    # =========================
    # Section Parsing
    # =========================

    def parse_sections(self, pages: List[Dict[str, Any]]) -> List[Section]:
        sections = []
        current_section = None

        for page in pages:
            page_number = page["page_number"]
            lines = page["text"].splitlines()

            for line in lines:
                match = self.SECTION_PATTERN.match(line)

                if match:
                    if current_section:
                        sections.append(self._finalize_section(current_section))

                    section_number = match.group(1)
                    title = match.group(3)

                    full_name = f"{section_number} {title}"
                    self.section_title_map[section_number] = full_name

                    current_section = {
                        "number": section_number,
                        "title": title,
                        "full_name": full_name,
                        "page_number": page_number,
                        "content": ""
                    }
                elif current_section:
                    current_section["content"] += line + "\n"

        if current_section:
            sections.append(self._finalize_section(current_section))

        return sections

    # =========================
    # Finalization
    # =========================

    def _finalize_section(self, data: Dict) -> Section:
        content = data["content"]

        hierarchy_tree = self.build_hierarchy_tree(data["number"])

        anchors = self.extract_anchors(content)
        shall_sentences = self.extract_shall_sentences(content)

        metadata = SectionMetadata(
            content_length=len(content),
            requirement_count=len(shall_sentences),
            reference_count=len(anchors),
            has_subsections="." in data["number"],
            depth=len(data["number"].split(".")),
            word_count=len(content.split())
        )

        return Section(
            id=f'section_{data["number"].replace(".", "_")}',
            hierarchy=data["full_name"],
            hierarchy_tree=hierarchy_tree,
            title=data["title"],
            anchors=anchors,
            shall_sentences=shall_sentences,
            page_number=data["page_number"],
            key_phrases=[],
            metadata=metadata,
            raw_content=content
        )

    # =========================
    # Output
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
                    "ancestors": s.hierarchy_tree.ancestors
                },
                "anchors": s.anchors,
                "shallSentences": s.shall_sentences,
                "pageNumber": s.page_number,
                "metadata": {
                    "contentLength": s.metadata.content_length,
                    "requirementCount": s.metadata.requirement_count,
                    "referenceCount": s.metadata.reference_count,
                    "hasSubsections": s.metadata.has_subsections,
                    "depth": s.metadata.depth,
                    "wordCount": s.metadata.word_count
                },
                "rawContent": s.raw_content
            })

        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        if output_path:
            Path(output_path).write_text(json_str, encoding="utf-8")

        return json_str


# =========================
# CLI
# =========================

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ocp_parser.py <ocp_pdf> [output.json]")
        return

    parser = OCPSpecificationParser(sys.argv[1])
    sections = parser.parse()
    output = sys.argv[2] if len(sys.argv) > 2 else "ocp_parsed_output.json"
    parser.to_json(sections, output)

    print(f"Parsed {len(sections)} sections")
    print(f"Output written to {output}")


if __name__ == "__main__":
    main()
