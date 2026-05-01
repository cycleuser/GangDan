"""Document downloader and indexer with image support."""

import sys
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import requests

from gangdan.core.config import CONFIG, get_proxies, detect_language
from gangdan.core.chroma_manager import ChromaManager
from gangdan.core.ollama_client import OllamaClient


# =============================================================================
# Documentation Sources - Using reliable raw GitHub URLs
# =============================================================================

DOC_SOURCES = {
    # Python Libraries
    "numpy": {
        "name": "NumPy",
        "urls": [
            "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/absolute_beginners.rst",
            "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/basics.creation.rst",
            "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/basics.indexing.rst",
        ],
    },
    "pandas": {
        "name": "Pandas",
        "urls": [
            "https://raw.githubusercontent.com/pandas-dev/pandas/main/doc/source/user_guide/10min.rst",
            "https://raw.githubusercontent.com/pandas-dev/pandas/main/doc/source/user_guide/indexing.rst",
        ],
    },
    "pytorch": {
        "name": "PyTorch",
        "urls": [
            "https://raw.githubusercontent.com/pytorch/pytorch/main/README.md",
            "https://raw.githubusercontent.com/pytorch/tutorials/main/beginner_source/basics/intro.py",
        ],
    },
    "scipy": {
        "name": "SciPy",
        "urls": [
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/index.rst",
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/optimize.rst",
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/interpolate.rst",
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/linalg.rst",
        ],
    },
    "sklearn": {
        "name": "Scikit-learn",
        "urls": [
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/README.rst",
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/getting_started.rst",
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/clustering.rst",
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/tree.rst",
        ],
    },
    "skimage": {
        "name": "Scikit-image",
        "urls": [
            "https://raw.githubusercontent.com/scikit-image/scikit-image/main/README.md",
            "https://raw.githubusercontent.com/scikit-image/scikit-image/main/doc/source/user_guide/getting_started.rst",
            "https://raw.githubusercontent.com/scikit-image/scikit-image/main/doc/source/user_guide/tutorial_segmentation.rst",
        ],
    },
    "sympy": {
        "name": "SymPy",
        "urls": [
            "https://raw.githubusercontent.com/sympy/sympy/master/README.md",
            "https://raw.githubusercontent.com/sympy/sympy/master/doc/src/tutorials/intro-tutorial/intro.rst",
            "https://raw.githubusercontent.com/sympy/sympy/master/doc/src/tutorials/intro-tutorial/basic_operations.rst",
        ],
    },
    "chempy": {
        "name": "ChemPy",
        "urls": [
            "https://raw.githubusercontent.com/bjodah/chempy/master/README.rst",
            "https://raw.githubusercontent.com/bjodah/chempy/master/CHANGES.rst",
        ],
    },
    "jupyter": {
        "name": "Jupyter",
        "urls": [
            "https://raw.githubusercontent.com/jupyter/notebook/main/README.md",
            "https://raw.githubusercontent.com/jupyterlab/jupyterlab/main/README.md",
            "https://raw.githubusercontent.com/ipython/ipython/main/README.rst",
        ],
    },
    "matplotlib": {
        "name": "Matplotlib",
        "urls": [
            "https://raw.githubusercontent.com/matplotlib/matplotlib/main/README.md",
            "https://raw.githubusercontent.com/matplotlib/matplotlib/main/doc/users/getting_started/index.rst",
        ],
    },
    "pyside6": {
        "name": "PySide6/Qt",
        "urls": [
            "https://raw.githubusercontent.com/pyside/pyside-setup/dev/README.md",
            "https://raw.githubusercontent.com/qt/qtbase/dev/README.md",
        ],
    },
    "pyqtgraph": {
        "name": "PyQtGraph",
        "urls": [
            "https://raw.githubusercontent.com/pyqtgraph/pyqtgraph/master/README.md",
            "https://raw.githubusercontent.com/pyqtgraph/pyqtgraph/master/doc/source/index.rst",
        ],
    },
    "tensorflow": {
        "name": "TensorFlow",
        "urls": [
            "https://raw.githubusercontent.com/tensorflow/tensorflow/master/README.md",
            "https://raw.githubusercontent.com/tensorflow/docs/master/site/en/guide/basics.ipynb",
        ],
    },
    # GPU Computing
    "cuda": {
        "name": "CUDA/PyCUDA",
        "urls": [
            "https://raw.githubusercontent.com/inducer/pycuda/main/README.rst",
            "https://raw.githubusercontent.com/inducer/pycuda/main/doc/source/tutorial.rst",
        ],
    },
    "opencl": {
        "name": "OpenCL/PyOpenCL",
        "urls": [
            "https://raw.githubusercontent.com/inducer/pyopencl/main/README.rst",
            "https://raw.githubusercontent.com/inducer/pyopencl/main/doc/source/index.rst",
        ],
    },
    # Programming Languages
    "rust": {
        "name": "Rust",
        "urls": [
            "https://raw.githubusercontent.com/rust-lang/book/main/src/ch01-00-getting-started.md",
            "https://raw.githubusercontent.com/rust-lang/book/main/src/ch03-00-common-programming-concepts.md",
            "https://raw.githubusercontent.com/rust-lang/book/main/src/ch04-00-understanding-ownership.md",
        ],
    },
    "javascript": {
        "name": "JavaScript",
        "urls": [
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/javascript/guide/introduction/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/javascript/guide/grammar_and_types/index.md",
        ],
    },
    "typescript": {
        "name": "TypeScript",
        "urls": [
            "https://raw.githubusercontent.com/microsoft/TypeScript/main/README.md",
            "https://raw.githubusercontent.com/microsoft/TypeScript-Website/v2/packages/documentation/copy/en/handbook-v2/Basics.md",
        ],
    },
    "c_lang": {
        "name": "C Language",
        "urls": [
            "https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-style.rst",
        ],
    },
    "cpp": {
        "name": "C++",
        "urls": [
            "https://raw.githubusercontent.com/isocpp/CppCoreGuidelines/master/CppCoreGuidelines.md",
        ],
    },
    "go": {
        "name": "Go/Golang",
        "urls": [
            "https://raw.githubusercontent.com/golang/go/master/README.md",
            "https://raw.githubusercontent.com/golang/go/master/doc/effective_go.html",
        ],
    },
    "html_css": {
        "name": "HTML/CSS",
        "urls": [
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/learn/html/introduction_to_html/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/learn/css/first_steps/index.md",
        ],
    },
    # Shell & Command Line
    "bash": {
        "name": "Bash Shell",
        "urls": [
            "https://raw.githubusercontent.com/dylanaraps/pure-bash-bible/master/README.md",
            "https://raw.githubusercontent.com/jlevy/the-art-of-command-line/master/README.md",
            "https://raw.githubusercontent.com/awesome-lists/awesome-bash/master/README.md",
        ],
    },
    "zsh": {
        "name": "Zsh Shell",
        "urls": [
            "https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/README.md",
            "https://raw.githubusercontent.com/unixorn/awesome-zsh-plugins/main/README.md",
        ],
    },
    "powershell": {
        "name": "PowerShell",
        "urls": [
            "https://raw.githubusercontent.com/PowerShell/PowerShell/master/README.md",
            "https://raw.githubusercontent.com/janikvonrotz/awesome-powershell/master/readme.md",
        ],
    },
    "fish": {
        "name": "Fish Shell",
        "urls": [
            "https://raw.githubusercontent.com/fish-shell/fish-shell/master/README.md",
            "https://raw.githubusercontent.com/jorgebucaran/awsm.fish/main/README.md",
        ],
    },
    "linux_commands": {
        "name": "Linux Commands",
        "urls": [
            "https://raw.githubusercontent.com/jlevy/the-art-of-command-line/master/README.md",
            "https://raw.githubusercontent.com/tldr-pages/tldr/main/README.md",
            "https://raw.githubusercontent.com/chubin/cheat.sh/master/README.md",
        ],
    },
    "git": {
        "name": "Git Commands",
        "urls": [
            "https://raw.githubusercontent.com/git/git/master/README.md",
            "https://raw.githubusercontent.com/git-tips/tips/master/README.md",
            "https://raw.githubusercontent.com/arslanbilal/git-cheat-sheet/master/README.md",
        ],
    },
    "docker": {
        "name": "Docker Commands",
        "urls": [
            "https://raw.githubusercontent.com/docker/docker.github.io/master/README.md",
            "https://raw.githubusercontent.com/wsargent/docker-cheat-sheet/master/README.md",
        ],
    },
    "kubectl": {
        "name": "Kubernetes/kubectl",
        "urls": [
            "https://raw.githubusercontent.com/kubernetes/kubectl/master/README.md",
            "https://raw.githubusercontent.com/dennyzhang/cheatsheet-kubernetes-A4/master/README.org",
        ],
    },
    # Animation & Motion Graphics
    "manim": {
        "name": "Manim (Math Animation)",
        "urls": [
            "https://raw.githubusercontent.com/ManimCommunity/manim/main/README.md",
            "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/index.rst",
            "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/quickstart.rst",
            "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/configuration.rst",
            "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/building_blocks.rst",
            "https://raw.githubusercontent.com/3b1b/manim/master/README.md",
        ],
    },
    "remotion": {
        "name": "Remotion (React Video)",
        "urls": [
            "https://raw.githubusercontent.com/remotion-dev/remotion/main/README.md",
            "https://raw.githubusercontent.com/remotion-dev/remotion/main/packages/docs/docs/index.md",
            "https://raw.githubusercontent.com/remotion-dev/remotion/main/packages/docs/docs/the-fundamentals.md",
            "https://raw.githubusercontent.com/remotion-dev/remotion/main/packages/docs/docs/terminology.md",
        ],
    },
    "html_animation": {
        "name": "HTML + Animation",
        "urls": [
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/html/element/canvas/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/canvas_api/tutorial/getting_started/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/canvas_api/tutorial/drawing_shapes/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/web_animations_api/using_the_web_animations_api/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/svg_api/tutorial/svg_getting_started/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/css/css_animations/using_css_animations/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/css/css_transitions/using_css_transitions/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/html/element/video/index.md",
        ],
    },
}


class DocManager:
    """Document downloader and indexer with image support."""

    def __init__(self, docs_dir: Path, chroma: ChromaManager, ollama: OllamaClient):
        self.docs_dir = docs_dir
        self.chroma = chroma
        self.ollama = ollama
        self._session = requests.Session()

    def download_source(self, source_name: str) -> Tuple[int, List[str]]:
        """Download documentation for a source."""
        if source_name not in DOC_SOURCES:
            print(f"[Download] Unknown source: {source_name}", file=sys.stderr)
            return 0, [f"Unknown source: {source_name}"]

        source = DOC_SOURCES[source_name]
        urls = source["urls"]
        downloaded = 0
        errors = []
        proxies = get_proxies()

        source_dir = self.docs_dir / source_name
        source_dir.mkdir(parents=True, exist_ok=True)

        print(f"[Download] Starting {source_name}: {len(urls)} URLs", file=sys.stderr)
        if proxies:
            print(
                f"[Download] Using proxy: {proxies.get('http', 'N/A')}", file=sys.stderr
            )

        for url in urls:
            filename = url.split("/")[-1]
            try:
                r = self._session.get(url, timeout=30, proxies=proxies)
                r.raise_for_status()
                content = r.text

                # Convert to markdown if needed
                if filename.endswith(".rst"):
                    filename = filename.replace(".rst", ".md")
                elif filename.endswith(".py") or filename.endswith(".ipynb"):
                    content = f"```python\n{content}\n```"
                    filename = filename.replace(".py", ".md").replace(".ipynb", ".md")
                elif filename.endswith(".html"):
                    filename = filename.replace(".html", ".md")
                elif filename.endswith(".texi"):
                    filename = filename.replace(".texi", ".md")
                elif filename.endswith(".cpp"):
                    content = f"```cpp\n{content}\n```"
                    filename = filename.replace(".cpp", ".md")
                elif not filename.endswith(".md"):
                    filename += ".md"

                filepath = source_dir / filename
                filepath.write_text(content, encoding="utf-8")
                downloaded += 1
                print(f"[Download]   OK: {filename}", file=sys.stderr)
            except Exception as e:
                err_msg = f"{filename}: {type(e).__name__}"
                errors.append(err_msg)
                print(f"[Download]   FAIL: {err_msg}", file=sys.stderr)

            time.sleep(0.2)

        print(
            f"[Download] Completed {source_name}: {downloaded} success, {len(errors)} errors",
            file=sys.stderr,
        )
        return downloaded, errors

    def index_source(
        self, source_name: str, process_images: bool = True, image_mode: str = "copy"
    ) -> Tuple[int, int, int]:
        """Index documents from a source into ChromaDB.

        Parameters
        ----------
        source_name : str
            Name of the knowledge base source.
        process_images : bool
            Whether to process images in markdown files.
        image_mode : str
            Image processing mode: "copy", "base64", or "reference".

        Returns
        -------
        Tuple[int, int, int]
            Number of files processed, chunks indexed, and images processed.
        """
        if self.chroma is None or self.chroma.client is None:
            print(
                f"[Index] Skipped {source_name} - ChromaDB not available",
                file=sys.stderr,
            )
            return 0, 0, 0
        if not CONFIG.embedding_model:
            print(
                f"[Index] Skipped {source_name} - no embedding model configured",
                file=sys.stderr,
            )
            return 0, 0, 0

        source_dir = self.docs_dir / source_name
        if not source_dir.exists():
            print(
                f"[Index] Skipped {source_name} - directory not found", file=sys.stderr
            )
            return 0, 0, 0

        files = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
        if not files:
            print(
                f"[Index] Skipped {source_name} - no markdown/text files found",
                file=sys.stderr,
            )
            return 0, 0, 0

        print(f"[Index] Processing {source_name}: {len(files)} files", file=sys.stderr)
        if process_images:
            print(f"[Index] Image mode: {image_mode}", file=sys.stderr)

        documents = []
        embeddings = []
        metadatas = []
        ids = []
        detected_languages = set()
        total_images = 0

        for filepath in files:
            content = filepath.read_text(encoding="utf-8")

            if process_images and filepath.suffix.lower() == ".md":
                content, img_count = self._process_document_images(
                    source_dir, filepath, content, image_mode
                )
                if img_count > 0:
                    total_images += img_count
                    print(
                        f"[Index]   {filepath.name}: processed {img_count} images",
                        file=sys.stderr,
                    )

            doc_lang = detect_language(content)
            detected_languages.add(doc_lang)
            print(
                f"[Index]   {filepath.name}: detected language = {doc_lang}",
                file=sys.stderr,
            )

            chunks = self._chunk_text(content, CONFIG.chunk_size, CONFIG.chunk_overlap)
            file_chunks = 0

            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                try:
                    emb = self.ollama.embed(chunk, CONFIG.embedding_model)
                    doc_id = hashlib.md5(f"{filepath.name}_{i}".encode()).hexdigest()

                    documents.append(chunk)
                    embeddings.append(emb)
                    metadatas.append(
                        {
                            "source": source_name,
                            "file": filepath.name,
                            "chunk": i,
                            "language": doc_lang,
                        }
                    )
                    ids.append(doc_id)
                    file_chunks += 1
                except Exception as e:
                    print(
                        f"[Index]   Error embedding chunk {i} of {filepath.name}: {e}",
                        file=sys.stderr,
                    )
                    continue

            print(f"[Index]   {filepath.name}: {file_chunks} chunks", file=sys.stderr)

        if documents:
            self.chroma.add_documents(
                source_name, documents, embeddings, metadatas, ids
            )
            print(
                f"[Index] Added {len(documents)} chunks to collection '{source_name}'",
                file=sys.stderr,
            )
            print(
                f"[Index] Languages detected: {', '.join(detected_languages)}",
                file=sys.stderr,
            )

        if total_images > 0:
            print(f"[Index] Total images processed: {total_images}", file=sys.stderr)

        return len(files), len(documents), total_images

    def _process_document_images(
        self, kb_dir: Path, source_path: Path, content: str, image_mode: str = "copy"
    ) -> Tuple[str, int]:
        """Process images in a markdown document.

        Parameters
        ----------
        kb_dir : Path
            Knowledge base directory.
        source_path : Path
            Source document path.
        content : str
            Document content.
        image_mode : str
            Image processing mode: "copy", "base64", or "reference".

        Returns
        -------
        Tuple[str, int]
            Updated content and number of images processed.
        """
        from gangdan.core.image_handler import ImageHandler, ImageProcessResult

        try:
            handler = ImageHandler(kb_dir)
            result = handler.process_document(
                content, source_path, embed_mode=image_mode
            )

            if result.copied_count > 0:
                source_path.write_text(result.updated_content, encoding="utf-8")

            # Always save manifest if there are images (even if not copied)
            if result.images:
                handler.save_image_manifest(source_path.name, result.images)
                print(
                    f"[Index]   {source_path.name}: saved manifest for {len(result.images)} images",
                    file=sys.stderr,
                )

            return result.updated_content, result.copied_count
        except Exception as e:
            print(f"[Index]   Error processing images: {e}", file=sys.stderr)
            return content, 0

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks.
        
        Parameters
        ----------
        text : str
            Text to chunk.
        chunk_size : int
            Size of each chunk in characters.
        overlap : int
            Number of overlapping characters between chunks.
            
        Returns
        -------
        List[str]
            List of text chunks.
        """
        if overlap >= chunk_size:
            overlap = max(0, chunk_size - 1)
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks

    def list_downloaded(self) -> List[Dict]:
        """List all downloaded documentation sources."""
        result = []
        if self.docs_dir.exists():
            for d in self.docs_dir.iterdir():
                if d.is_dir():
                    files = list(d.glob("*.md"))
                    result.append({"name": d.name, "files": len(files)})
        return result
