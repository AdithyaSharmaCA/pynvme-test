import fitz  # PyMuPDF
import re
import json


# -----------------------------
# Extract key phrases (UNCHANGED LOGIC, cleaned)
# -----------------------------
def extract_keyphrases(text, section_name):
    key_phrases = [section_name]

    command_patterns = [
        r'([A-Z][a-zA-Z\s]+(?:command|Command))',
        r'((?:Admin|I/O|Fabrics)\s+command)',
        r'command\s+([A-Z][a-zA-Z\s]+)'
    ]

    for pattern in command_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            if isinstance(m, tuple):
                m = m[0]
            if len(m.strip()) > 3:
                key_phrases.append(m.strip())

    queue_patterns = [
        r'((?:I/O\s+)?(?:Submission|Completion)\s+Queue)',
        r'((?:Admin\s+)?(?:Submission|Completion)\s+Queue)',
        r'(\w+\s+Queue)'
    ]

    for pattern in queue_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for q in matches:
            if len(q.strip()) > 3:
                key_phrases.append(q.strip())

    register_patterns = [
        r'(Offset\s+\w+h:\s+[A-Za-z\s]+)',
        r'([A-Z][a-zA-Z\s]+(?:Register|register))'
    ]

    for pattern in register_patterns:
        matches = re.findall(pattern, text)
        for r in matches:
            if len(r.strip()) > 3:
                key_phrases.append(r.strip())

    return list(set(key_phrases))


# -----------------------------
# Build TOC hierarchy once
# -----------------------------
def build_toc_index(doc):
    toc = doc.get_toc()
    toc_index = []

    active_levels = {}

    for level, title, page in toc:
        active_levels[level] = title

        # Remove deeper levels
        for l in list(active_levels.keys()):
            if l > level:
                del active_levels[l]

        toc_index.append({
            "page": page,
            "hierarchy": title,
            "hierarchy_tree": list(active_levels.values())
        })

    return toc_index


# -----------------------------
# Resolve section by page number
# -----------------------------
def resolve_section(toc_index, page_number):
    current = {
        "hierarchy": "General",
        "hierarchy_tree": ["General"]
    }

    for entry in toc_index:
        if entry["page"] <= page_number:
            current = entry
        else:
            break

    return current["hierarchy"], current["hierarchy_tree"]


# -----------------------------
# Extract SHALL + context
# -----------------------------
def extract_shall_sentences(paragraph):
    sentences = re.split(r'(?<=[.!?])\s+', paragraph)

    results = []

    for i, sentence in enumerate(sentences):
        if re.search(r'\bshall\b', sentence, re.IGNORECASE):
            results.append({
                "shall_sentence": sentence.strip(),
                "before_shall": sentences[i - 1].strip() if i > 0 else None,
                "after_shall": sentences[i + 1].strip() if i < len(sentences) - 1 else None
            })

    return results


# -----------------------------
# MAIN FUNCTION
# -----------------------------
def extract_OCP_requirements(pdf_path):
    doc = fitz.open(pdf_path)

    toc_index = build_toc_index(doc)

    shall_pattern = re.compile(r'\bshall\b', re.IGNORECASE)
    anchor_pattern = re.compile(
        r'(see|refer to)\s+(section|table|figure)\s+[0-9.]+',
        re.IGNORECASE
    )

    sectional_nodes = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        blocks = page.get_text("blocks")

        section_name, hierarchy_tree = resolve_section(
            toc_index, page_index + 1
        )

        for block in blocks:
            paragraph = block[4].strip()
            if not paragraph:
                continue

            if not shall_pattern.search(paragraph):
                continue

            shall_items = extract_shall_sentences(paragraph)
            anchors = list(set(anchor_pattern.findall(paragraph)))
            key_phrases = extract_keyphrases(paragraph, section_name)

            for item in shall_items:
                sectional_nodes.append({
                    "hierarchy": section_name,
                    "hierarchy_tree": hierarchy_tree,
                    "page_number": page_index + 1,
                    "shall_sentence": item["shall_sentence"],
                    "before_shall": item["before_shall"],
                    "after_shall": item["after_shall"],
                    "anchors": anchors,
                    "key_phrases": key_phrases
                })

    return sectional_nodes


# -----------------------------
# OPTIONAL: run & dump
# -----------------------------
if __name__ == "__main__":
    pdf_path = "./DSSDocp.pdf"
    output = extract_OCP_requirements(pdf_path)

    with open("./output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
