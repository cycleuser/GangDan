#!/usr/bin/env python3
"""Search arXiv for 'vector calculus', download full articles, convert to markdown,
and create a knowledge base named '矢量积分'.
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Ensure gangdan package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gangdan.core.preprint_fetcher import ArxivPreprintFetcher, PreprintMetadata
from gangdan.core.preprint_converter import PreprintConverter
from gangdan.core.config import DATA_DIR, DOCS_DIR, sanitize_kb_name, save_user_kb

KB_DISPLAY_NAME = "矢量积分"
SEARCH_QUERY = "vector calculus"
MAX_RESULTS = 20


def main():
    internal_name = sanitize_kb_name(KB_DISPLAY_NAME)
    print(f"Internal KB name: {internal_name}")

    # Step 1: Search arXiv
    print(f"\n{'='*60}")
    print(f"Searching arXiv for: {SEARCH_QUERY}")
    print(f"{'='*60}")

    fetcher = ArxivPreprintFetcher(max_results=MAX_RESULTS)
    papers = fetcher.search(SEARCH_QUERY)

    print(f"Found {len(papers)} papers")
    for i, p in enumerate(papers):
        fmt = p.preferred_format
        print(f"  [{i+1}] {p.preprint_id}: {p.short_title}")
        print(f"       HTML={p.has_html}, TeX={p.has_tex}, preferred={fmt}")
        if i >= 9:
            print(f"  ... and {len(papers) - 10} more")
            break

    if not papers:
        print("No papers found. Exiting.")
        return

    # Step 2: Create KB directory
    kb_dir = DOCS_DIR / internal_name
    if kb_dir.exists():
        print(f"\nRemoving existing KB directory: {kb_dir}")
        shutil.rmtree(kb_dir, ignore_errors=True)
    kb_dir.mkdir(parents=True, exist_ok=True)

    # Step 3: Download & convert each paper
    print(f"\n{'='*60}")
    print(f"Downloading & converting full articles...")
    print(f"{'='*60}")

    converter = PreprintConverter(fallback_to_pdf=True)
    documents = {}
    converted_count = 0

    for i, paper in enumerate(papers):
        print(f"\n[{i+1}/{len(papers)}] {paper.preprint_id}: {paper.title[:60]}...")
        print(f"  Preferred format: {paper.preferred_format}")

        output_dir = Path(tempfile.mkdtemp(prefix=f"gangdan_{paper.preprint_id}_"))
        success = False

        # Try HTML first (best quality for conversion to markdown)
        if paper.has_html and paper.html_url:
            print(f"  Trying HTML: {paper.html_url}")
            try:
                result = converter.convert_from_url(
                    paper.html_url,
                    content_type="html",
                    output_dir=output_dir,
                    preprint_id=paper.preprint_id,
                )
                if result.success and result.markdown_path and Path(result.markdown_path).exists():
                    md_path = result.markdown_path
                    print(f"  HTML -> Markdown: {md_path}")
                    success = True
                else:
                    print(f"  HTML conversion failed: {result.error}")
            except Exception as e:
                print(f"  HTML download failed: {e}")

        # Fallback to TeX source
        if not success and paper.has_tex and paper.tex_source_url:
            print(f"  Trying TeX: {paper.tex_source_url}")
            try:
                result = converter.convert_from_url(
                    paper.tex_source_url,
                    content_type="tex",
                    output_dir=output_dir,
                    preprint_id=paper.preprint_id,
                )
                if result.success and result.markdown_path and Path(result.markdown_path).exists():
                    md_path = result.markdown_path
                    print(f"  TeX -> Markdown: {md_path}")
                    success = True
                else:
                    print(f"  TeX conversion failed: {result.error}")
            except Exception as e:
                print(f"  TeX download failed: {e}")

        # Fallback to PDF
        if not success and paper.pdf_url:
            print(f"  Trying PDF: {paper.pdf_url}")
            try:
                result = converter.convert_from_url(
                    paper.pdf_url,
                    content_type="pdf",
                    output_dir=output_dir,
                    preprint_id=paper.preprint_id,
                )
                if result.success and result.markdown_path and Path(result.markdown_path).exists():
                    md_path = result.markdown_path
                    print(f"  PDF -> Markdown: {md_path}")
                    success = True
                else:
                    print(f"  PDF conversion failed: {result.error}")
            except Exception as e:
                print(f"  PDF download failed: {e}")

        if not success:
            print(f"  FAILED: All formats failed for {paper.preprint_id}")
            continue

        # Copy markdown to KB directory
        dest_name = f"{paper.preprint_id}.md"
        dest_path = kb_dir / dest_name
        try:
            md_content = Path(md_path).read_text(encoding="utf-8")
            # Add metadata header
            header = f"# {paper.title}\n\n"
            header += f"**Authors:** {paper.authors_str}\n\n"
            header += f"**arXiv ID:** [{paper.preprint_id}]({paper.url})\n\n"
            header += f"**Published:** {paper.published_date}\n\n"
            header += f"**Abstract:** {paper.abstract}\n\n"
            header += "---\n\n"
            dest_path.write_text(header + md_content, encoding="utf-8")

            doc_id = paper.preprint_id
            documents[doc_id] = {
                "doc_id": doc_id,
                "title": paper.title,
                "source_type": "paper",
                "source_id": paper.preprint_id,
                "source_platform": "arxiv",
                "markdown_path": str(dest_path),
                "content_preview": paper.abstract[:500] if paper.abstract else "",
                "authors": paper.authors,
                "published_date": paper.published_date,
                "url": paper.url,
                "tags": [],
                "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            converted_count += 1
            print(f"  Saved to KB: {dest_name}")
        except Exception as e:
            print(f"  Error saving markdown: {e}")

        # Small delay to avoid rate limiting
        time.sleep(1)

    # Step 4: Save documents manifest
    manifest = {
        "kb_id": internal_name,
        "internal_name": internal_name,
        "documents": documents,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (kb_dir / "documents.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Step 5: Register KB in user_kbs.json
    save_user_kb(internal_name, KB_DISPLAY_NAME, converted_count, languages=["en"])

    print(f"\n{'='*60}")
    print(f"Knowledge Base '{KB_DISPLAY_NAME}' created successfully!")
    print(f"  Internal name: {internal_name}")
    print(f"  Directory: {kb_dir}")
    print(f"  Documents: {converted_count}/{len(papers)} converted")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
