import asyncio

import pytest
import pytest_asyncio

from manga_grabber import usagi
from manga_grabber.exceptions import TitleNotFoundError


pytestmark = [
    pytest.mark.asyncio(loop_scope="module")
]

loop: asyncio.AbstractEventLoop


TITLES = [
    "hot_first_kiss",
]


@pytest_asyncio.fixture(loop_scope="module", params=TITLES)
async def chapters(request):
    global loop
    loop = asyncio.get_running_loop()
    title = request.param
    manga_url = f"https://web.usagi.one/{title}/"
    async with usagi.UsagiOne(manga_url) as manga:
        chapters = await manga.get_chapters()
        yield chapters, manga


async def test_non_existent_title():
    manga_url = "https://web.usagi.one/invalid-title/"
    async with usagi.UsagiOne(manga_url) as manga:
        with pytest.raises(TitleNotFoundError):
            await manga.get_chapters()


async def test_get_chapters(chapters):
    chapters, _ = chapters
    assert isinstance(chapters, list)
    assert len(chapters) > 0
    for chapter in chapters:
        assert "number" in chapter
        assert "volume" in chapter
        assert "branches" in chapter


async def test_download_chapter(tmp_path, chapters):
    chapters, manga = chapters
    chapter = chapters[0]
    chapter_dir = tmp_path / f"vol{chapter['volume']}_ch{chapter['number']}"
    await manga.download_chapter(
        chapter["number"],
        chapter["volume"],
        chapter_dir,
        chapter["branches"][0]["branch_id"]
    )
    assert chapter_dir.exists()
    assert any(chapter_dir.iterdir())
