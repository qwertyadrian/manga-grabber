import asyncio

import pytest
import pytest_asyncio

from manga_grabber import mangalib
from manga_grabber.exceptions import TitleNotFoundError


pytestmark = [
    pytest.mark.asyncio(loop_scope="module")
]

loop: asyncio.AbstractEventLoop


TITLES = [
    "188415--imasara-desu-ga-osananajimi-o-suki-ni-natteshimaimashita",
    "1284--relife",
    "5686--the-story-about-how-sweet-my-husband-is",
    "66652--kokuhaku-series",
]


@pytest_asyncio.fixture(loop_scope="module", params=TITLES)
async def chapters(request):
    global loop
    loop = asyncio.get_running_loop()
    title = request.param
    manga_url = f"https://mangalib.me/ru/{title}/"
    async with mangalib.MangaLib(manga_url) as manga:
        chapters = await manga.get_chapters()
        yield chapters, manga


async def test_non_existent_title():
    manga_url = "https://mangalib.me/ru/9999-invalid-title/"
    async with mangalib.MangaLib(manga_url) as manga:
        with pytest.raises(TitleNotFoundError):
            await manga.get_chapters()


@pytest.mark.parametrize("title", [
    "19973--hello-hello-andhello",
    "12066--yunagi-no-machi-sakura-no-kuni",
])
async def test_unavailable_title(title):
    manga_url = f"https://mangalib.me/ru/{title}/"
    async with mangalib.MangaLib(manga_url) as manga:
        chapters = await manga.get_chapters()
        assert len(chapters) == 0


async def test_get_chapters(chapters):
    chapters, _ = chapters
    assert isinstance(chapters, list)
    assert len(chapters) > 0
    for chapter in chapters:
        assert "number" in chapter
        assert "volume" in chapter
        assert "branches" in chapter


async def test_get_chapter_info(chapters):
    chapters, manga = chapters
    chapter = chapters[0]
    chapter_info = await manga.get_chapter_info(chapter["number"], chapter["volume"])
    assert isinstance(chapter_info, dict)
    assert chapter_info["number"] == chapter["number"]
    assert chapter_info["volume"] == chapter["volume"]
    # assert chapter_info["branches"] == chapter["branches"]
    assert chapter_info["manga_id"] == manga.manga_id
    assert isinstance(chapter_info["pages"], list)
    assert len(chapter_info["pages"]) > 0


async def test_download_chapter(tmp_path, chapters):
    chapters, manga = chapters
    chapter = chapters[0]
    chapter_dir = tmp_path / f"vol{chapter['volume']}_ch{chapter['number']}"
    await manga.download_chapter(chapter["number"], chapter["volume"], chapter_dir)
    assert chapter_dir.exists()
    assert any(chapter_dir.iterdir())
