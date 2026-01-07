"""
OCP 2.0 Specification Parser
Extracts structured information from OCP PDF specifications for test case generation.

Requirements:
pip install PyPDF2 pdfplumber pymupdf spacy nltk
python -m spacy download en_core_web_sm
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import fitz  # PyMuPDF
import pdfplumber


@dataclass
class HierarchyTree:
    """Represents the hierarchical structure of a section."""
    current: str
    parent: Optional[str]
    grandparent: Optional[str]
    ancestors: List[str]


@dataclass
class SectionMetadata:
    """Metadata about a section."""
    content_length: int
    requirement_count: int
    reference_count: int
    has_subsections: bool
    depth: int
    word_count: int


@dataclass
class Section:
    """Represents a parsed section from the specification."""
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


class OCPSpecificationParser:
    """Parser for OCP 2.0 specifications."""
    
    # Regex patterns for extraction
    SECTION_PATTERN = re.compile(r'^(\d+(?:\.\d+)*\.?)\s+([A-Z][^\n]+)', re.MULTILINE)
    SHALL_PATTERN = re.compile(r'[^.!?]*\bshall\b[^.!?]*[.!?]', re.IGNORECASE)
    ANCHOR_PATTERNS = [
        re.compile(r'see\s+[Ss]ection\s+[\d.]+', re.IGNORECASE),
        re.compile(r'refer\s+to\s+[Ss]ection\s+[\d.]+', re.IGNORECASE),
        re.compile(r'defined\s+in\s+[Ss]ection\s+[\d.]+', re.IGNORECASE),
        re.compile(r'[Ss]ection\s+[\d.]+'),
        re.compile(r'see\s+[\d.]+', re.IGNORECASE),
    ]
    
    # Technical term patterns for key phrase extraction
    KEY_PHRASE_PATTERNS = [
        re.compile(r'\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}\b'),  # Capitalized terms
        re.compile(r'\b(?:power|thermal|cooling|rack|server|module|interface|protocol|'
                   r'connector|voltage|current|temperature|efficiency|airflow|'
                   r'management|controller|sensor|fan|supply)\b', re.IGNORECASE),
        re.compile(r'\b\d+(?:\.\d+)?(?:\s*(?:V|A|W|°C|°F|mm|cm|m|GB|TB|MHz|GHz|Gbps|'
                   r'kg|lbs|%|dB))\b'),  # Technical measurements
    ]
    
    def __init__(self, pdf_path: str):
        """Initialize the parser with a PDF file path."""
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    def extract_text_with_pages(self) -> List[Dict[str, Any]]:
        """Extract text from PDF with page numbers using multiple methods for robustness."""
        pages_data = []
        
        try:
            # Try pdfplumber first (better for structured text)
            with pdfplumber.open(self.pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text:
                        pages_data.append({
                            'page_number': page_num,
                            'text': text,
                            'method': 'pdfplumber'
                        })
        except Exception as e:
            print(f"pdfplumber failed: {e}, trying PyMuPDF...")
            
            # Fallback to PyMuPDF
            doc = fitz.open(self.pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                pages_data.append({
                    'page_number': page_num + 1,
                    'text': text,
                    'method': 'pymupdf'
                })
            doc.close()
        
        return pages_data
    
    def build_hierarchy_tree(self, hierarchy: str) -> HierarchyTree:
        """Build hierarchy tree with parent, grandparent, and ancestors."""
        parts = hierarchy.split('.')
        ancestors = ['.'.join(parts[:i+1]) for i in range(len(parts) - 1)]
        
        return HierarchyTree(
            current=hierarchy,
            parent='.'.join(parts[:-1]) if len(parts) > 1 else None,
            grandparent='.'.join(parts[:-2]) if len(parts) > 2 else None,
            ancestors=ancestors
        )
    
    def extract_anchors(self, text: str) -> List[str]:
        """Extract all cross-references and section anchors."""
        anchors = []
        for pattern in self.ANCHOR_PATTERNS:
            matches = pattern.findall(text)
            anchors.extend(matches)
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(anchors))
    
    def extract_shall_sentences(self, text: str) -> List[str]:
        """Extract requirement sentences containing 'shall'."""
        matches = self.SHALL_PATTERN.findall(text)
        # Clean up and filter
        shall_sentences = [s.strip() for s in matches if len(s.strip()) > 15]
        return list(dict.fromkeys(shall_sentences))  # Remove duplicates
    
    def extract_key_phrases(self, text: str) -> List[str]:
        """Extract key technical terms and phrases."""
        phrases = set()
        
        for pattern in self.KEY_PHRASE_PATTERNS:
            matches = pattern.findall(text)
            for match in matches:
                cleaned = match.strip()
                if 3 < len(cleaned) < 50:  # Reasonable length
                    phrases.add(cleaned)
        
        # Sort by frequency in text (simple heuristic)
        phrase_freq = [(p, text.lower().count(p.lower())) for p in phrases]
        phrase_freq.sort(key=lambda x: x[1], reverse=True)
        
        return [p for p, _ in phrase_freq[:15]]  # Top 15 phrases
    
    def parse_sections(self, pages_data: List[Dict[str, Any]]) -> List[Section]:
        """Parse the document into hierarchical sections."""
        sections = []
        current_section = None
        
        for page_data in pages_data:
            page_num = page_data['page_number']
            text = page_data['text']
            lines = text.split('\n')
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Try to match section header
                match = self.SECTION_PATTERN.match(line)
                
                if match:
                    # Save previous section
                    if current_section:
                        sections.append(self._finalize_section(current_section))
                    
                    # Start new section
                    hierarchy = match.group(1).rstrip('.')
                    title = match.group(2).strip()
                    
                    current_section = {
                        'hierarchy': hierarchy,
                        'title': title,
                        'page_number': page_num,
                        'content': '',
                        'start_page': page_num
                    }
                elif current_section:
                    # Add content to current section
                    current_section['content'] += line + '\n'
                
                i += 1
        
        # Don't forget the last section
        if current_section:
            sections.append(self._finalize_section(current_section))
        
        return sections
    
    def _finalize_section(self, section_data: Dict) -> Section:
        """Convert raw section data to Section object with all metadata."""
        hierarchy = section_data['hierarchy']
        content = section_data['content'].strip()
        
        # Build hierarchy tree
        hierarchy_tree = self.build_hierarchy_tree(hierarchy)
        
        # Extract various components
        anchors = self.extract_anchors(content)
        shall_sentences = self.extract_shall_sentences(content)
        key_phrases = self.extract_key_phrases(content)
        
        # Build metadata
        metadata = SectionMetadata(
            content_length=len(content),
            requirement_count=len(shall_sentences),
            reference_count=len(anchors),
            has_subsections='.' in hierarchy,
            depth=len(hierarchy.split('.')),
            word_count=len(content.split())
        )
        
        # Create section ID
        section_id = f"section_{hierarchy.replace('.', '_')}"
        
        return Section(
            id=section_id,
            hierarchy=hierarchy,
            title=section_data['title'],
            hierarchy_tree=hierarchy_tree,
            anchors=anchors,
            shall_sentences=shall_sentences,
            page_number=section_data['page_number'],
            key_phrases=key_phrases,
            metadata=metadata,
            raw_content=content[:1000] + ('...' if len(content) > 1000 else '')
        )
    
    def parse(self) -> List[Section]:
        """Main parsing method."""
        print(f"Parsing PDF: {self.pdf_path}")
        pages_data = self.extract_text_with_pages()
        print(f"Extracted text from {len(pages_data)} pages")
        
        sections = self.parse_sections(pages_data)
        print(f"Parsed {len(sections)} sections")
        
        return sections
    
    def to_json(self, sections: List[Section], output_path: Optional[str] = None) -> str:
        """Convert sections to JSON format."""
        # Convert dataclasses to dictionaries
        json_data = []
        for section in sections:
            section_dict = {
                'id': section.id,
                'hierarchy': section.hierarchy,
                'title': section.title,
                'hierarchyTree': {
                    'current': section.hierarchy_tree.current,
                    'parent': section.hierarchy_tree.parent,
                    'grandparent': section.hierarchy_tree.grandparent,
                    'ancestors': section.hierarchy_tree.ancestors
                },
                'anchors': section.anchors,
                'shallSentences': section.shall_sentences,
                'pageNumber': section.page_number,
                'keyPhrases': section.key_phrases,
                'metadata': {
                    'contentLength': section.metadata.content_length,
                    'requirementCount': section.metadata.requirement_count,
                    'referenceCount': section.metadata.reference_count,
                    'hasSubsections': section.metadata.has_subsections,
                    'depth': section.metadata.depth,
                    'wordCount': section.metadata.word_count
                },
                'rawContent': section.raw_content
            }
            json_data.append(section_dict)
        
        json_str = json.dumps(json_data, indent=2, ensure_ascii=False)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            print(f"JSON saved to: {output_path}")
        
        return json_str
    
    def generate_statistics(self, sections: List[Section]) -> Dict[str, Any]:
        """Generate statistics about the parsed document."""
        total_requirements = sum(s.metadata.requirement_count for s in sections)
        total_references = sum(s.metadata.reference_count for s in sections)
        max_depth = max(s.metadata.depth for s in sections) if sections else 0
        
        return {
            'total_sections': len(sections),
            'total_requirements': total_requirements,
            'total_references': total_references,
            'max_hierarchy_depth': max_depth,
            'sections_with_requirements': sum(1 for s in sections if s.metadata.requirement_count > 0),
            'average_requirements_per_section': total_requirements / len(sections) if sections else 0,
            'total_words': sum(s.metadata.word_count for s in sections)
        }


def main():
    """Example usage."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ocp_parser.py <path_to_ocp_pdf> [output_json_path]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'ocp_parsed_output.json'
    
    # Initialize parser
    parser = OCPSpecificationParser(pdf_path)
    
    # Parse the document
    sections = parser.parse()
    
    # Generate JSON output
    parser.to_json(sections, output_path)
    
    # Print statistics
    stats = parser.generate_statistics(sections)
    print("\n=== Parsing Statistics ===")
    for key, value in stats.items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    
    # Print sample of first section
    if sections:
        print("\n=== Sample Section ===")
        sample = sections[0]
        print(f"ID: {sample.id}")
        print(f"Hierarchy: {sample.hierarchy}")
        print(f"Title: {sample.title}")
        print(f"Requirements: {len(sample.shall_sentences)}")
        print(f"References: {len(sample.anchors)}")
        if sample.shall_sentences:
            print(f"\nFirst Requirement: {sample.shall_sentences[0][:100]}...")


if __name__ == '__main__':
    main()