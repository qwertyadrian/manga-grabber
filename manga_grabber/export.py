import urllib.parse
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Literal

import natsort
from bs4 import BeautifulSoup
from fpdf import FPDF
from PIL import Image

from .mangalib import HentaiLib, MangaLib, RanobeLib


def img_to_cbz(output_dir: Path):
    """
    Creates a CBZ archive from the contents of the specified directory

    :param output_dir: Directory containing manga chapter pages
    :return: Path to the created CBZ file
    """
    cbz_path = output_dir.with_suffix(".cbz")
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for page in natsort.natsorted(output_dir.iterdir(), alg=natsort.ns.REAL):
            zipf.write(page, arcname=page.name)
    return cbz_path


def img_to_pdf(output_dir: Path):
    """
    Creates a PDF file from the contents of the specified directory

    :param output_dir: Directory containing manga chapter pages
    :return: Path to the created PDF file
    """
    pdf_path = output_dir.with_suffix(".pdf")
    pdf = FPDF(unit="pt")  # Use points as unit for better control over dimensions

    # Sort pages by name to maintain order
    pages = natsort.natsorted(output_dir.iterdir(), alg=natsort.ns.REAL)

    for page in pages:
        # Open the image file to get its dimensions
        with Image.open(page) as image:
            width, height = image.size
            # Convert pixels to points (1 pixel = 0.75 points)
            pdf.add_page(format=(width * 0.75, height * 0.75))
            pdf.image(image, x=0, y=0, w=width * 0.75, h=height * 0.75)

    pdf.output(str(pdf_path))
    return pdf_path


def html_to_pdf(output_dir: Path):
    """
    Creates a PDF file from the HTML content in the specified directory

    :param output_dir: Directory containing the HTML file and assets
    :return: Path to the created PDF file
    """
    pdf_path = output_dir.with_suffix(".pdf")
    pdf = FPDF(unit="pt")

    fonts_path = files("manga_grabber.fonts")
    pdf.add_font("DejaVuSerif", "", fonts_path / "DejaVuSerif.ttf")
    pdf.add_font("DejaVuSerif", "B", fonts_path / "DejaVuSerif-Bold.ttf")
    pdf.add_font("DejaVuSerif", "I", fonts_path / "DejaVuSerif-Italic.ttf")
    pdf.add_font("DejaVuSerif", "BI", fonts_path / "DejaVuSerif-BoldItalic.ttf")
    pdf.add_font(fname=fonts_path / "DejaVuSans.ttf")
    pdf.set_fallback_fonts(["DejaVuSans"])

    pdf.add_page()

    # Load the HTML file
    html_file = output_dir / "index.html"
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    # Set images width to fit the page
    for img in soup.find_all("img"):
        img_path = output_dir / img["src"]
        img["width"] = int(pdf.epw)
        img["src"] = str(img_path)
    # Convert the modified HTML back to a string
    html_content = str(soup)

    pdf.write_html(html_content, font_family="DejaVuSerif")

    pdf.output(str(pdf_path))
    return pdf_path


async def download_title(
    manga_url: str,
    output_dir: Path,
    branch_id: int | None = None,
    token: str | None = None,
    cbz: bool = False,
    pdf: bool = False,
    save_mode: Literal["chapter", "volume", "all"] = "chapter",
):
    """
    Downloads all chapters of a manga from MangaLib and saves them to the specified directory

    :param manga_url: URL of the manga on MangaLib
    :param output_dir: Directory where the manga chapters will be saved
    :param branch_id: ID of translation branch (optional, for multi-branch titles)
    :param token: Optional API token for authenticated requests
    :param cbz: If True, chapters will be archived as CBZ files
    :param pdf: If True, chapters will be archived as PDF files
    :param save_mode: How to save chapters, can be 'chapter' (one chapter per dir/file),
    'volume' (one volume per dir/file), or 'all' (one dir/file for all chapters)
    """
    manga_parsed_url = urllib.parse.urlparse(manga_url)
    if manga_parsed_url.hostname == "hentailib.me":
        manga_lib_class = HentaiLib
    elif manga_parsed_url.hostname == "ranobelib.me":
        manga_lib_class = RanobeLib
    else:
        manga_lib_class = MangaLib

    async with manga_lib_class(manga_parsed_url.path, token) as manga_lib:
        chapters = await manga_lib.get_chapters()
        for chapter in chapters:
            branch_found = any((branch["branch_id"] == branch_id for branch in chapter["branches"]))
            if not branch_found:
                continue

            print(
                f"Downloading chapter {chapter['number']} from volume {chapter['volume']}..."
            )
            match save_mode:
                case "chapter":
                    chapter_dir = (
                        output_dir / f"vol{chapter['volume']}_ch{chapter['number']}"
                    )
                    prefix = ""
                case "volume":
                    chapter_dir = output_dir / f"vol{chapter['volume']}"
                    prefix = f"ch{chapter['number']}_"
                case "all":
                    chapter_dir = output_dir
                    prefix = f"vol{chapter['volume']}_ch{chapter['number']}_"
            await manga_lib.download_chapter(
                chapter["number"],
                chapter["volume"],
                chapter_dir,
                branch_id=branch_id,
                prefix=prefix,
            )
            print(
                f"Chapter {chapter['number']} from volume {chapter['volume']} downloaded."
            )
            if cbz:
                cbz_path = img_to_cbz(chapter_dir)
                print(
                    f"Chapter {chapter['number']} from volume {chapter['volume']} archived as {cbz_path}."
                )
            if pdf:
                if (chapter_dir / "index.html").exists():
                    pdf_path = html_to_pdf(chapter_dir)
                else:
                    pdf_path = img_to_pdf(chapter_dir)
                print(
                    f"Chapter {chapter['number']} from volume {chapter['volume']} archived as {pdf_path}."
                )
