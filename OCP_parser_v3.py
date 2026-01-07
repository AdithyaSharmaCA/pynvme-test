"""
OCP 2.0 Specification Parser
Lossless + Named Hierarchy + Minimal Contextual Requirements + Anchors
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
class Requirement:
    requirement_id: str
    shall_text: str
    context_before: List[str]
    context_after: List[str]
    anchor: Optional[str]
    page_number: int
    hierarchy: str
    parent_hierarchy: Optional[str]


@dataclass
class Section:
    id: str
    hierarchy: str
    hierarchy_tree: HierarchyTree
    title: str
    requirements: List[Requirement]
    page_number: int
    metadata: SectionMetadata
    raw_content: str


# =========================
# Parser
# =========================

class OCPSpecificationParser:
    """
    Lossless OCP Parser with LLM-ready minimal contextual requirements
    """

    SECTION_PATTERN = re.compile(r'^(\d+(?:\.\d+)*)(\s+)(.+)$')
    SHALL_PATTERN = re.compile(r'\bshall\b', re.IGNORECASE)

    # ONLY explicit anchors starting with "(see ...)"
    ANCHOR_PATTERN = re.compile(
        r'\(see\b[^)]*\)',
        re.IGNORECASE
    )

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
            current=self.section_title_map.get(section_number, section_number),
            parent=ancestors[-1] if ancestors else None,
            grandparent=ancestors[-2] if len(ancestors) >= 2 else None,
            ancestors=ancestors
        )

    # =========================
    # Contextual Requirement Extraction
    # =========================

    def extract_requirements_with_context(
        self,
        lines: List[str],
        section_id: str,
        hierarchy: str,
        parent_hierarchy: Optional[str],
        page_number: int
    ) -> List[Requirement]:

        requirements: List[Requirement] = []

        for idx, line in enumerate(lines):
            if not self.SHALL_PATTERN.search(line):
                continue

            # -------- Context BEFORE: single previous non-empty line --------
            before = []
            i = idx - 1
            while i >= 0:
                if lines[i].strip():
                    before = [lines[i]]
                    break
                i -= 1

            # -------- Context AFTER: single next non-empty line --------
            after = []
            i = idx + 1
            while i < len(lines):
                if lines[i].strip():
                    after = [lines[i]]
                    break
                i += 1

            # -------- Anchor detection (critical) --------
            anchor_match = self.ANCHOR_PATTERN.search(line)
            if not anchor_match and after:
                anchor_match = self.ANCHOR_PATTERN.search(after[0])

            anchor = anchor_match.group(0) if anchor_match else None

            # -------- Preserve requirement ID format --------
            req_id = f"{section_id}_req_{len(requirements) + 1}"

            requirements.append(
                Requirement(
                    requirement_id=req_id,
                    shall_text=line,
                    context_before=before,
                    context_after=after,
                    anchor=anchor,
                    page_number=page_number,
                    hierarchy=hierarchy,
                    parent_hierarchy=parent_hierarchy
                )
            )

        return requirements

    # =========================
    # Parsing
    # =========================

    def parse(self) -> List[Section]:
        pages = self.extract_text_with_pages()
        sections = []
        current = None

        for page in pages:
            page_number = page["page_number"]
            lines = page["text"].splitlines()

            for line in lines:
                match = self.SECTION_PATTERN.match(line)

                if match:
                    if current:
                        sections.append(self._finalize_section(current))

                    number = match.group(1)
                    title = match.group(3)
                    full_name = f"{number} {title}"
                    self.section_title_map[number] = full_name

                    current = {
                        "number": number,
                        "title": title,
                        "full_name": full_name,
                        "page_number": page_number,
                        "lines": []
                    }
                elif current:
                    current["lines"].append(line)

        if current:
            sections.append(self._finalize_section(current))

        return sections

    # =========================
    # Finalization
    # =========================

    def _finalize_section(self, data: Dict) -> Section:
        lines = data["lines"]
        content = "\n".join(lines)

        hierarchy_tree = self.build_hierarchy_tree(data["number"])
        section_id = f'section_{data["number"].replace(".", "_")}'

        requirements = self.extract_requirements_with_context(
            lines=lines,
            section_id=section_id,
            hierarchy=data["full_name"],
            parent_hierarchy=hierarchy_tree.parent,
            page_number=data["page_number"]
        )

        metadata = SectionMetadata(
            content_length=len(content),
            requirement_count=len(requirements),
            reference_count=len(self.ANCHOR_PATTERN.findall(content)),
            has_subsections="." in data["number"],
            depth=len(data["number"].split(".")),
            word_count=len(content.split())
        )

        return Section(
            id=section_id,
            hierarchy=data["full_name"],
            hierarchy_tree=hierarchy_tree,
            title=data["title"],
            requirements=requirements,
            page_number=data["page_number"],
            metadata=metadata,
            raw_content=content
        )

    # =========================
    # JSON Output
    # =========================

    def to_json(self, sections: List[Section], output_path: str):
        data = []

        for s in sections:
            data.append({
                "id": s.id,
                "hierarchy": s.hierarchy,
                "hierarchyTree": s.hierarchy_tree.__dict__,
                "pageNumber": s.page_number,
                "requirements": [
                    {
                        "requirementId": r.requirement_id,
                        "shallText": r.shall_text,
                        "anchor": r.anchor,
                        "context": {
                            "before": r.context_before,
                            "after": r.context_after
                        },
                        "sectionHierarchy": r.hierarchy,
                        "parentHierarchy": r.parent_hierarchy,
                        "pageNumber": r.page_number
                    }
                    for r in s.requirements
                ],
                "metadata": s.metadata.__dict__,
                "rawContent": s.raw_content
            })

        Path(output_path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
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
    sections = parser.parse()
    output = sys.argv[2] if len(sys.argv) > 2 else "ocp_llm_ready.json"
    parser.to_json(sections, output)

    print(f"Parsed {len(sections)} sections")
    print(f"Output written to {output}")


if __name__ == "__main__":
    main()
