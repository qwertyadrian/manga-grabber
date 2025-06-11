import asyncio
import re
import zipfile
from pathlib import Path

import aiohttp


class MangaLib:
    """A class to interact with the MangaLib API and download manga chapters"""

    api_base_url = "https://api.cdnlibs.org/api"
    resource_base_url = "https://img2.imglib.info"

    def __init__(self, manga_url: str, token: str = None):
        """
        Initialize the MangaLib instance

        :param manga_url: URL of the manga on MangaLib
        :param token: Optional API token for authenticated requests
        """
        self._session = None
        self._token = token
        self._headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0"
        }
        if token is not None:
            self._headers["Authorization"] = f"Bearer {token}"

        # Extract the manga ID from the URL
        self.manga_id = int(re.findall(r"/((\d+)-?-?[\w-]*)", manga_url)[0][1])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @property
    async def session(self):
        """Get the aiohttp session, creating it if it doesn't exist or is closed"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def close(self):
        """Close the aiohttp session if it exists and is not closed"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_chapters(self):
        """Fetch the list of chapters and additional info for the manga"""
        session = await self.session
        async with session.get(
            f"{self.api_base_url}/manga/{self.manga_id}/chapters"
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch chapters: {response.status}")
            return (await response.json())["data"]

    async def get_chapter_info(self, chapter: int, volume: int):
        """Fetch detailed information about a specific chapter of the manga"""
        session = await self.session
        async with session.get(
            f"{self.api_base_url}/manga/{self.manga_id}/chapter",
            params=dict(number=chapter, volume=volume),
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch chapter info: {response.status}")
            return (await response.json())["data"]

    async def download_chapter(self, chapter: int, volume: int, output_dir: Path):
        """
        Download all pages of a specific chapter and save them to the specified directory

        :param chapter: Chapter number to download
        :param volume: Volume number to download
        :param output_dir: Directory where the chapter pages will be saved
        """
        ch = await self.get_chapter_info(chapter, volume)

        if not output_dir.exists():
            output_dir.mkdir(parents=True)

        tasks = []
        for page in ch["pages"]:
            url = f"{self.resource_base_url}/{page['url']}"
            tasks.append(
                self._download_page(
                    await self.session,
                    url,
                    output_dir / f"{page['slug']:02d}_{page['image']}",
                )
            )
        return await asyncio.gather(*tasks)

    @staticmethod
    async def _download_page(session, url, path: Path):
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download page: {response.status}")
            fd = path.open("wb")
            async for chunk in response.content.iter_chunked(1024):
                fd.write(chunk)
            fd.close()


async def download_title(
    manga_url: str, output_dir: Path, token: str = None, cbz: bool = False
):
    """
    Downloads all chapters of a manga from MangaLib and saves them to the specified directory

    :param manga_url: URL of the manga on MangaLib
    :param output_dir: Directory where the manga chapters will be saved
    :param token: Optional API token for authenticated requests
    :param cbz: If True, chapters will be archived as CBZ files
    """
    async with MangaLib(manga_url, token) as manga_lib:
        chapters = await manga_lib.get_chapters()
        for chapter in chapters:
            print(
                f"Downloading chapter {chapter['number']} from volume {chapter['volume']}..."
            )
            await manga_lib.download_chapter(
                chapter["number"],
                chapter["volume"],
                output_dir / f"v{chapter['volume']}_c{chapter['number']}",
            )
            print(
                f"Chapter {chapter['number']} from volume {chapter['volume']} downloaded."
            )
            if cbz:
                cbz_path = output_dir / f"v{chapter['volume']}_c{chapter['number']}.cbz"
                with zipfile.ZipFile(
                    cbz_path, "w", compression=zipfile.ZIP_DEFLATED
                ) as zipf:
                    for page in (
                        output_dir / f"v{chapter['volume']}_c{chapter['number']}"
                    ).iterdir():
                        zipf.write(page, arcname=page.name)
                print(
                    f"Chapter {chapter['number']} from volume {chapter['volume']} archived as {cbz_path}."
                )
