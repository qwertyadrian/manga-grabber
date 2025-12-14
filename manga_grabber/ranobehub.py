import asyncio
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from .base import BaseGrabber, register_grabber
from .exceptions import GrabberException

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@register_grabber("ranobehub.org")
class RanobeHub(BaseGrabber):
    base_url: str = "https://ranobehub.org"

    def __init__(self, title_url: str, token: str | None = None):
        """
        :param title_url: URL of the title to be grabbed
        :param token: Not used
        """
        super().__init__(title_url, token)
        self._headers["Referer"] = "https://ranobehub.org"
        match = re.search(r"/(\d+)-?([\w-]*)", title_url)
        if not match:
            raise GrabberException("Could not parse title ID and name from URL")
        self.title_id = int(match.group(1))
        self.title_name = match.group(2)

    async def get_chapters(self) -> list:
        session = await self.session
        api_url = f"{self.base_url}/api/ranobe/{self.title_id}/contents"
        async with session.get(api_url) as response:
            response.raise_for_status()
            data = await response.json()

        return [
            {
                "id": ch["id"],
                "volume": vol["num"],
                "number": ch["num"],
                "name": ch["name"],
                "url": ch["url"],
                "branches": [{"branch_id": 0}],
            }
            for vol in data["volumes"]
            for ch in vol["chapters"]
        ]

    async def download_chapter(
        self,
        chapter: int | float,
        volume: int,
        output_dir: Path,
        branch_id: int = 0,
        prefix: str = "",
    ):
        """
        Download all pages of a specific chapter and save them to the specified directory

        :param chapter: Chapter number to download
        :param volume: Volume number to download
        :param output_dir: Directory where the chapter pages will be saved
        :param branch_id: Not used
        :param prefix: Prefix for the downloaded files
        """
        session = await self.session
        chapter_url = f"{self.base_url}/ranobe/{self.title_id}/{volume}/{chapter}"
        async with session.get(chapter_url) as response:
            response.raise_for_status()
            soup = BeautifulSoup(await response.text(), "html.parser")

        assets_path = output_dir / "assets"
        assets_path.mkdir(parents=True, exist_ok=True)

        tasks = []
        for img in soup.find_all("img", {"data-media-id": True}):
            media_id = img["data-media-id"]
            img_url = f"{self.base_url}/api/media/{media_id}"
            img_path = assets_path / media_id
            tasks.append(self._download_file(session, img_url, img_path))
            img["src"] = f"assets/{media_id}"

        if small_img := soup.find("img", {"class": "ui small centered bordered rounded image"}):
            img_url = small_img["src"].replace("/small", "")
            img_path = assets_path / img_url.split("/")[-2]
            tasks.append(self._download_file(session, img_url, img_path))
            small_img["src"] = f"assets/{img_url.split('/')[-2]}"

        for ad_div in soup.select("div.ads-desktop, div.chapter-hoticons"):
            ad_div.decompose()

        title_name = soup.find("h1", {"class": "ui header"}).string
        content_div = soup.find("div", {"class": "ui text container"})

        html_content = f"""<!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <title>Том {volume} Глава {chapter} — {title_name}</title>
        </head>
        <body>
        {content_div.prettify()}
        </body>
        </html>"""

        file_path = output_dir / f"{prefix}index.html"
        file_path.write_text(html_content, encoding="utf-8")

        await asyncio.gather(*tasks)
