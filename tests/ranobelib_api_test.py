import asyncio

import pytest
import pytest_asyncio

from manga_grabber import mangalib


pytestmark = [
    pytest.mark.asyncio(loop_scope="module")
]

loop: asyncio.AbstractEventLoop


TITLES = [
    "6689--ascendance-of-a-bookworm-novel",
    "191618--imasara-desu-ga-osananajimi-wo-suki-ni-natte-shimaimashita",
    "62340--the-angel-next-door-spoils-me-rotten",
    "24729--shuumatsu-nani-shitemasu-ka-isogashii-desuka-sukutte-moratte-ii-desuka-1-novel",
    "239592--houkago-famiresu-de-kurasu-no-ano-ko-to-light-novel",
]


@pytest_asyncio.fixture(loop_scope="module", params=TITLES)
async def chapters(request):
    global loop
    loop = asyncio.get_running_loop()
    title = request.param
    manga_url = f"https://ranobelib.me/ru/{title}/"
    async with mangalib.RanobeLib(manga_url) as manga:
        chapters = await manga.get_chapters()
        yield chapters, manga


async def test_non_existent_title():
    manga_url = "https://ranobelib.me/ru/9999-invalid-title/"
    async with mangalib.RanobeLib(manga_url) as manga:
        with pytest.raises(Exception):
            await manga.get_chapters()


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
    assert "content" in chapter_info
    assert isinstance(chapter_info["content"], (str, dict))
    assert len(chapter_info["content"]) > 0
    assert isinstance(chapter_info["attachments"], list)


async def test_download_chapter(tmp_path, chapters):
    chapters, manga = chapters
    chapter = chapters[0]
    chapter_dir = tmp_path / f"vol{chapter['volume']}_ch{chapter['number']}"
    await manga.download_chapter(
        chapter["number"],
        chapter["volume"],
        chapter_dir,
    )
    assert chapter_dir.exists()
    assert any(chapter_dir.iterdir())
