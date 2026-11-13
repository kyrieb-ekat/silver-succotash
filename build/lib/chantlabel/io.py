"""Loading the page image (PDF with one embedded raster, or any image file)."""
import os
import subprocess
import tempfile

import cv2
import numpy as np


def load_page(path):
    """Return the full-resolution BGR image of a page.

    PDFs are expected to wrap a single raster scan (as library digitisations
    usually do); the embedded image is extracted losslessly with ``pdfimages``
    if available, otherwise with PyMuPDF.
    """
    if path.lower().endswith(".pdf"):
        return _load_pdf(path)
    im = cv2.imread(path, cv2.IMREAD_COLOR)
    if im is None:
        raise IOError(f"could not read image {path}")
    return im


def _load_pdf(path):
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(["pdfimages", "-j", "-f", "1", "-l", "1", path, os.path.join(td, "img")],
                           check=True, capture_output=True)
            files = sorted(os.listdir(td))
            if files:
                # largest embedded image on page 1
                best = max(files, key=lambda f: os.path.getsize(os.path.join(td, f)))
                im = cv2.imread(os.path.join(td, best), cv2.IMREAD_COLOR)
                if im is not None:
                    return im
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("Install poppler-utils (pdfimages) or PyMuPDF to read PDFs") from e
    doc = fitz.open(path)
    page = doc[0]
    imgs = page.get_images(full=True)
    if imgs:
        xref = max(imgs, key=lambda i: i[2] * i[3])[0]
        data = doc.extract_image(xref)["image"]
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    pix = page.get_pixmap(dpi=300)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)
