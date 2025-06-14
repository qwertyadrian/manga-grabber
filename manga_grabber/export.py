import urllib.parse
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Literal

import natsort
from bs4 import BeautifulSoup
from fpdf import FPDF
from fpdf.outline import TableOfContents
from PIL import Image

from .mangalib import HentaiLib, MangaLib, RanobeLib
from .utils import find_font


def img_to_cbz(img_dir: Path):
    """
    Creates a CBZ archive from the contents of the specified directory

    :param img_dir: Directory containing manga chapter pages
    :return: Path to the created CBZ file
    """
    cbz_path = img_dir.with_suffix(".cbz")
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for page in natsort.natsorted(img_dir.iterdir(), alg=natsort.ns.REAL):
            zipf.write(page, arcname=page.name)
    return cbz_path


def img_to_pdf(img_path: Path):
    """
    Creates a PDF file from the contents of the specified directory

    :param img_path: Directory containing manga chapter pages
    :return: Path to the created PDF file
    """
    pdf_path = img_path.with_suffix(".pdf")
    pdf = FPDF(unit="pt")  # Use points as unit for better control over dimensions

    # Sort pages by name to maintain order
    pages = natsort.natsorted(img_path.iterdir(), alg=natsort.ns.REAL)

    for page in pages:
        # Open the image file to get its dimensions
        with Image.open(page) as image:
            width, height = image.size
            # Convert pixels to points (1 pixel = 0.75 points)
            pdf.add_page(format=(width * 0.75, height * 0.75))
            pdf.image(image, x=0, y=0, w=width * 0.75, h=height * 0.75)

    pdf.output(str(pdf_path))
    return pdf_path


def html_to_pdf(html_dir: Path):
    """
    Creates a PDF file from the HTML content in the specified directory

    :param html_dir: Directory containing the HTML file and assets
    :return: Path to the created PDF file
    """
    html_files = natsort.natsorted(html_dir.glob("*.html"), alg=natsort.ns.REAL)

    pdf_path = html_dir.with_suffix(".pdf")
    pdf = FPDF(unit="pt")
    pdf.add_page()
    if len(html_files) > 1:
        toc = TableOfContents()
        pdf.insert_toc_placeholder(toc.render_toc, allow_extra_pages=True)

    # Add fonts
    fonts_path = files("manga_grabber.fonts")
    pdf.add_font("DejaVuSerif", "", fonts_path / "DejaVuSerif.ttf")
    pdf.add_font("DejaVuSerif", "B", fonts_path / "DejaVuSerif-Bold.ttf")
    pdf.add_font("DejaVuSerif", "I", fonts_path / "DejaVuSerif-Italic.ttf")
    pdf.add_font("DejaVuSerif", "BI", fonts_path / "DejaVuSerif-BoldItalic.ttf")
    pdf.add_font(fname=fonts_path / "DejaVuSans.ttf")
    fallback_fonts = ["DejaVuSans"]
    # Set fallback fonts for CJK characters
    for family in ("Noto Sans CJK JP", "Yu Gothic"):
        if cjk_font := find_font(family, "Regular"):
            pdf.add_font(fname=cjk_font)
            fallback_fonts.append(cjk_font.stem)

    pdf.set_fallback_fonts(fallback_fonts)

    for html_file in html_files:
        # Load the HTML file
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")
        # Set images width to fit the page
        for img in soup.find_all("img"):
            img_path = html_dir / img["src"]
            img["width"] = int(pdf.epw)
            img["src"] = str(img_path)
        # Convert the modified HTML back to a string
        html_content = str(soup)

        pdf.write_html(html_content, font_family="DejaVuSerif")
        pdf.add_page()

    pdf.output(str(pdf_path))
    return pdf_path


async def download_title(
    manga_url: str,
    output_dir: Path,
    *,
    branch_id: int | None = None,
    token: str | None = None,
    from_chapter: int | float = 0,
    from_volume: int = 0,
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
    :param from_chapter: Chapter number to start downloading from
    :param from_volume: Volume number to start downloading from
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
            # Check if the volume and chapter numbers are within the specified ranges
            if (
                int(chapter["volume"]) < from_volume
                or float(chapter["number"]) < from_chapter
            ):
                continue

            branch_found = any(
                (branch["branch_id"] == branch_id for branch in chapter["branches"])
            )
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
                if any(chapter_dir.glob("*.html")):
                    pdf_path = html_to_pdf(chapter_dir)
                else:
                    pdf_path = img_to_pdf(chapter_dir)
                print(
                    f"Chapter {chapter['number']} from volume {chapter['volume']} archived as {pdf_path}."
                )
