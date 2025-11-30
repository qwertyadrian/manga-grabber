import asyncio
import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from .base import BaseGrabber, register_grabber
from .exceptions import ChapterInfoError, GrabberException, TitleNotFoundError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@register_grabber("web.usagi.one")
class UsagiOne(BaseGrabber):
    base_url: str = "https://web.usagi.one"

    def __init__(self, title_url: str, token: str | None = None):
        """
        :param title_url: URL of the title to be grabbed
        :param token: Not used
        """
        super().__init__(title_url, token)
        self._headers["Referer"] = self.base_url
        self.title_name = self.title_url.rstrip("/").split("/")[3]

    async def get_chapters(self) -> list:
        """Fetch the list of chapters and additional info for the manga"""
        session = await self.session
        async with session.get(self.title_url) as resp:
            if resp.status == 404:
                raise TitleNotFoundError(f"Title {self.title_name} not found")
            if resp.status != 200:
                raise GrabberException(f"Failed to fetch chapters: {resp.status}")

            soup = BeautifulSoup(await resp.text(), "html.parser")
            chapters = [
                {
                    "volume": int(chapter["data-vol"]),
                    "number": float(chapter["data-num"]) / 10,
                    "url": self.base_url + chapter.a["href"],
                    "branches": self._get_translations(
                        chapter.a.get("data-translations", '[{"personId": 0}]')
                    ),
                }
                for chapter in soup.find_all("td", {"class": "item-title"})
            ]
            return list(reversed(chapters))

    async def download_chapter(
        self,
        chapter: int,
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
        :param branch_id: ID of translation
        :param prefix: Prefix for the downloaded files
        """
        chapters = await self.get_chapters()

        found = next(
            (c for c in chapters if c["number"] == chapter and c["volume"] == volume),
            None,
        )
        if not found:
            raise ChapterInfoError(f"Chapter {chapter} from volume {volume} not found")

        # prepare chapter URL with translation if requested
        ch_url = found["url"]
        if branch_id > 0:
            for br in found["branches"]:
                if br["branch_id"] == branch_id:
                    ch_url += f"?tran={branch_id}"
                    break

        session = await self.session
        async with session.get(ch_url) as response:
            if response.status != 200:
                raise GrabberException(
                    f"Failed to fetch chapter page: {response.status}"
                )
            soup = BeautifulSoup(await response.text(), "html.parser")
            script_tag = soup.find(
                "script",
                string=lambda text: text and "rm_h.readerInit(chapterInfo" in text,
            )
            if not script_tag:
                raise ChapterInfoError(
                    "Could not find pages information in chapter page"
                )

            # Extract pages information from the script tag
            pages_data = re.search(
                r"rm_h\.readerInit\(chapterInfo, (\[\[.*\]\]), .*\)", script_tag.string
            )
            pages = json.loads(pages_data.group(1).replace("'", '"'))

        output_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        for num, page in enumerate(pages):
            url = page[0] + page[2]
            url = url.split("?")[0] if "one-way.work" in url else url
            name = url.split("/")[-1].split("?")[0]
            tasks.append(
                self._download_file(
                    await self.session,
                    url,
                    output_dir / f"{prefix}p{num:02d}_{name}",
                )
            )
        return await asyncio.gather(*tasks)

    @staticmethod
    def _get_translations(translations: str) -> list[dict]:
        translations = json.loads(translations)
        for translation in translations:
            translation["branch_id"] = translation.pop("personId")
        return translations
