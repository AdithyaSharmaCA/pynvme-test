import os
import re
import gc
import json
import uuid
import shutil
import subprocess

from pathlib import Path

import fitz
import torch

from PIL import Image
from docx import Document

from transformers import (
    AutoProcessor,
    AutoModelForImageTextToText
)

# ============================================================
# CONFIG
# ============================================================

DOCX_PATH = "NVMe-2-0.docx"

OUTPUT_JSON = "final_output.json"

MODEL_PATH = "/path/to/Qwen-VL"

PAGE_RENDER_DIR = Path("./rendered_pages")
TABLE_IMAGE_DIR = Path("./table_images")
TABLE_JSON_DIR = Path("./table_json")

PAGE_RENDER_DIR.mkdir(exist_ok=True)
TABLE_IMAGE_DIR.mkdir(exist_ok=True)
TABLE_JSON_DIR.mkdir(exist_ok=True)

# ============================================================
# HELPERS
# ============================================================

def generate_id():

    return str(uuid.uuid4())[:8]


def heading_level(style_name):

    m = re.search(r"Heading\s*(\d+)", style_name)

    if m:
        return int(m.group(1))

    return 1


# ============================================================
# DOCX → PDF
# ============================================================

def convert_docx_to_pdf(docx_path):

    output_dir = Path("./tmp_pdf")

    output_dir.mkdir(exist_ok=True)

    subprocess.run([
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(docx_path)
    ])

    pdf_path = output_dir / (
        Path(docx_path).stem + ".pdf"
    )

    return pdf_path


# ============================================================
# PDF → PAGE IMAGES
# ============================================================

def render_pdf_pages(pdf_path):

    pdf = fitz.open(pdf_path)

    rendered_pages = []

    for page_num in range(len(pdf)):

        page = pdf[page_num]

        pix = page.get_pixmap(
            matrix=fitz.Matrix(3, 3)
        )

        image_path = (
            PAGE_RENDER_DIR /
            f"page_{page_num+1}.png"
        )

        img = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        img.save(image_path)

        rendered_pages.append(str(image_path))

    return rendered_pages


# ============================================================
# VLM TABLE PARSER
# ============================================================

class VLMParser:

    def __init__(self, model_path):

        self.processor = AutoProcessor.from_pretrained(
            model_path,
            trust_remote_code=True
        )

        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto"
        )

    def clean_output(self, text):

        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.DOTALL
        )

        text = re.sub(r"```json", "", text)
        text = re.sub(r"```", "", text)

        return text.strip()

    def parse_table(self, image_path):

        image = Image.open(image_path).convert("RGB")

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image
                    },
                    {
                        "type": "text",
                        "text": """
Extract this table into structured JSON.

Preserve:
- merged cells
- headers
- row ordering
- hierarchy

Return valid JSON only.
"""
                    }
                ]
            }
        ]

        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False
        )

        inputs = self.processor(
            text=[text],
            images=[image],
            return_tensors="pt"
        ).to("cuda")

        output = self.model.generate(
            **inputs,
            max_new_tokens=8192,
            do_sample=False
        )

        generated = output[0][inputs.input_ids.shape[1]:]

        response = self.processor.decode(
            generated,
            skip_special_tokens=True
        )

        response = self.clean_output(response)

        start_obj = response.find("{")
        start_arr = response.find("[")

        starts = [
            x for x in [start_obj, start_arr]
            if x != -1
        ]

        if starts:
            response = response[min(starts):]

        try:
            parsed = json.loads(response)

        except:

            parsed = {
                "raw_output": response
            }

        del output
        del inputs

        torch.cuda.empty_cache()
        gc.collect()

        return parsed


# ============================================================
# TABLE SCREENSHOT EXTRACTOR
# ============================================================

class TableScreenshotExtractor:

    def __init__(self):

        self.current_page = 0

    def estimate_table_region(
        self,
        table_index,
        page_image_path
    ):

        """
        Placeholder heuristic.

        In production:
        use layout detection or
        Office XML coordinates.
        """

        image = Image.open(page_image_path)

        w, h = image.size

        top = int(h * 0.2)
        bottom = int(h * 0.8)

        cropped = image.crop(
            (50, top, w - 50, bottom)
        )

        out_path = (
            TABLE_IMAGE_DIR /
            f"table_{table_index}.png"
        )

        cropped.save(out_path)

        return str(out_path)


# ============================================================
# DOCX HIERARCHY PARSER
# ============================================================

class DOCXHierarchyParser:

    def __init__(self, docx_path):

        self.document = Document(docx_path)

        self.root = {
            "title": "ROOT",
            "children": [],
            "content": []
        }

        self.stack = []

    def current_section(self):

        if self.stack:
            return self.stack[-1]

        return self.root

    def add_section(self, title, level):

        node = {
            "id": generate_id(),
            "section_name": title,
            "level": level,
            "content": [],
            "children": []
        }

        while (
            self.stack and
            self.stack[-1]["level"] >= level
        ):
            self.stack.pop()

        if self.stack:
            self.stack[-1]["children"].append(node)
        else:
            self.root["children"].append(node)

        self.stack.append(node)

    def parse(self):

        blocks = self.document.element.body.iterchildren()

        for block in blocks:

            # ====================================================
            # PARAGRAPH
            # ====================================================

            if block.tag.endswith("p"):

                para = next(
                    p for p in self.document.paragraphs
                    if p._p is block
                )

                text = para.text.strip()

                if not text:
                    continue

                style_name = para.style.name

                if style_name.lower().startswith("heading"):

                    level = heading_level(style_name)

                    self.add_section(
                        text,
                        level
                    )

                else:

                    self.current_section()["content"].append({
                        "type": "paragraph",
                        "text": text
                    })

            # ====================================================
            # TABLE PLACEHOLDER
            # ====================================================

            elif block.tag.endswith("tbl"):

                self.current_section()["content"].append({
                    "type": "table_placeholder",
                    "table_id": generate_id()
                })

        return self.root


# ============================================================
# MAIN PIPELINE
# ============================================================

class UnifiedPipeline:

    def __init__(
        self,
        docx_path,
        model_path
    ):

        self.docx_path = docx_path

        self.vlm = VLMParser(model_path)

        self.table_extractor = (
            TableScreenshotExtractor()
        )

    def inject_tables(
        self,
        node,
        rendered_pages,
        table_counter=[0]
    ):

        new_content = []

        for item in node["content"]:

            # ====================================================
            # PARAGRAPH
            # ====================================================

            if item["type"] == "paragraph":

                new_content.append(item)

            # ====================================================
            # TABLE
            # ====================================================

            elif item["type"] == "table_placeholder":

                idx = table_counter[0]

                page_image = rendered_pages[
                    min(
                        idx,
                        len(rendered_pages) - 1
                    )
                ]

                screenshot_path = (
                    self.table_extractor
                    .estimate_table_region(
                        idx,
                        page_image
                    )
                )

                table_json = self.vlm.parse_table(
                    screenshot_path
                )

                json_out = (
                    TABLE_JSON_DIR /
                    f"table_{idx}.json"
                )

                with open(json_out, "w") as f:

                    json.dump(
                        table_json,
                        f,
                        indent=2,
                        ensure_ascii=False
                    )

                new_content.append({

                    "type": "table",

                    "table_id":
                        item["table_id"],

                    "image_path":
                        screenshot_path,

                    "table_json_path":
                        str(json_out),

                    "data":
                        table_json
                })

                table_counter[0] += 1

        node["content"] = new_content

        for child in node["children"]:

            self.inject_tables(
                child,
                rendered_pages,
                table_counter
            )

    def run(self):

        # ========================================================
        # STEP 1
        # DOCX HIERARCHY
        # ========================================================

        parser = DOCXHierarchyParser(
            self.docx_path
        )

        hierarchy = parser.parse()

        # ========================================================
        # STEP 2
        # DOCX → PDF
        # ========================================================

        pdf_path = convert_docx_to_pdf(
            self.docx_path
        )

        # ========================================================
        # STEP 3
        # RENDER PAGES
        # ========================================================

        rendered_pages = render_pdf_pages(
            pdf_path
        )

        # ========================================================
        # STEP 4
        # TABLE EXTRACTION
        # ========================================================

        self.inject_tables(
            hierarchy,
            rendered_pages
        )

        # ========================================================
        # STEP 5
        # FINAL OUTPUT
        # ========================================================

        with open(
            OUTPUT_JSON,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                hierarchy,
                f,
                indent=2,
                ensure_ascii=False
            )

        print("\nDone.")

        return hierarchy


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    pipeline = UnifiedPipeline(
        DOCX_PATH,
        MODEL_PATH
    )

    pipeline.run()