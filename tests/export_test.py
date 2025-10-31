import os

import pytest
import pytest_asyncio

from manga_grabber.export import download_title, img_to_cbz, img_to_pdf, html_to_pdf


pytestmark = [
    pytest.mark.asyncio(loop_scope="module"),
]

TOKEN = os.environ.get("TOKEN")


@pytest.fixture(scope="session")
def output_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("output-")


@pytest_asyncio.fixture(
    scope="session",
    params=[
        "https://mangalib.me/ru/manga/13124--machigatte-ita-no-waoredattanda",
        "https://ranobelib.me/ru/29610--itai-no-itai-no-tonde-yuke",
        "https://ranobelib.me/ru/25000--kimi-no-suizou-wo-tabetai-yoru-sumino",
        "https://hentailib.me/ru/234290--couple-under-the-rain",
    ],
)
async def downloaded_files(request, output_dir):
    title_url = request.param
    title_output = output_dir / title_url.split("/")[-1]
    await download_title(
        title_url,
        title_output,
        token=TOKEN,
        save_mode="volume" if "ranobelib.me" in title_url else "chapter",
    )
    assert any(title_output.iterdir()), "No files were downloaded"

    return title_output


def test_save_as_cbz(downloaded_files):
    chapter_dirs = [d for d in downloaded_files.iterdir() if d.is_dir()]
    assert len(chapter_dirs) > 0, "No files were downloaded"

    for chapter_dir in chapter_dirs:
        if any(chapter_dir.glob("*.html")):
            pytest.skip(f"{chapter_dir.parent.name} is ranobe, skipping CBZ test")
        cbz_path = img_to_cbz(chapter_dir)
        assert cbz_path.exists(), f"CBZ file {cbz_path} was not created"


def test_save_as_pdf(downloaded_files):
    chapter_dirs = [d for d in downloaded_files.iterdir() if d.is_dir()]
    assert len(chapter_dirs) > 0, "No files were downloaded"

    for chapter_dir in chapter_dirs:
        if any(chapter_dir.glob("*.html")):
            pdf_path = html_to_pdf(chapter_dir)
        else:
            pdf_path = img_to_pdf(chapter_dir)
        assert pdf_path.exists(), f"PDF file {pdf_path} was not created"
