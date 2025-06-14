import asyncio
import re
from abc import ABC, abstractmethod
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup


class BaseLib(ABC):
    """Base class for *Lib classes"""

    api_base_url: str = "https://api.cdnlibs.org/api"
    resource_base_url: str = "https://img2.imglib.info"

    def __init__(self, manga_url: str, token: str | None = None):
        """
        Initialize the *Lib instance

        :param manga_url: URL of the manga on MangaLib
        :param token: Optional API token for authenticated requests
        """
        self._session: aiohttp.ClientSession | None = None
        self._connector = aiohttp.TCPConnector(limit=20)
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
    async def session(self) -> aiohttp.ClientSession:
        """Get the aiohttp session, creating it if it doesn't exist or is closed"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers, connector=self._connector
            )
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

    async def get_chapter_info(
        self, chapter: int, volume: int, branch_id: int | None = None
    ):
        """Fetch detailed information about a specific chapter of the manga"""
        session = await self.session
        params = {"number": chapter, "volume": volume}
        if branch_id is not None:
            params["branch_id"] = branch_id
        async with session.get(
            f"{self.api_base_url}/manga/{self.manga_id}/chapter",
            params=params,
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch chapter info: {response.status}")
            return (await response.json())["data"]

    @staticmethod
    async def _download_file(session, url, path: Path):
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download page: {response.status}")
            with path.open("wb") as fd:
                async for chunk in response.content.iter_chunked(1024):
                    fd.write(chunk)

    @abstractmethod
    async def download_chapter(
        self,
        chapter: int,
        volume: int,
        output_dir: Path,
        branch_id: int | None = None,
        prefix: str = "",
    ):
        pass


class MangaLib(BaseLib):
    """A class to interact with the MangaLib API and download manga chapters"""

    async def download_chapter(
        self,
        chapter: int,
        volume: int,
        output_dir: Path,
        branch_id: int | None = None,
        prefix: str = "",
    ):
        """
        Download all pages of a specific chapter and save them to the specified directory

        :param chapter: Chapter number to download
        :param volume: Volume number to download
        :param output_dir: Directory where the chapter pages will be saved
        :param branch_id: ID of translation branch (optional, for multi-branch titles)
        :param prefix: Prefix for the downloaded files
        """
        ch = await self.get_chapter_info(chapter, volume, branch_id)

        if not output_dir.exists():
            output_dir.mkdir(parents=True)

        tasks = []
        for page in ch["pages"]:
            url = f"{self.resource_base_url}/{page['url']}"
            tasks.append(
                self._download_file(
                    await self.session,
                    url,
                    output_dir / f"{prefix}p{page['slug']:02d}_{page['image']}",
                )
            )
        return await asyncio.gather(*tasks)


class HentaiLib(MangaLib):
    resource_base_url = "https://img2h.imgslib.link"

    def __init__(self, manga_url: str, token: str | None = None):
        super().__init__(manga_url, token)
        self._headers["Referer"] = "https://hentailib.me/"


class RanobeLib(BaseLib):
    resource_base_url = "https://ranobelib.me"

    async def download_chapter(
        self,
        chapter: int,
        volume: int,
        output_dir: Path,
        branch_id: int | None = None,
        prefix: str = "",
    ):
        """
        Download all pages of a specific chapter and save them to the specified directory

        :param chapter: Chapter number to download
        :param volume: Volume number to download
        :param output_dir: Directory where the chapter pages will be saved
        :param branch_id: ID of translation branch (optional, for multi-branch titles)
        :param prefix: Prefix for the downloaded files
        """
        ch = await self.get_chapter_info(chapter, volume, branch_id)

        output_dir.mkdir(parents=True, exist_ok=True)

        file = output_dir / "index.html"
        assets_path = output_dir / "assets"
        assets_path.mkdir(parents=True, exist_ok=True)

        attachments = ch.get("attachments", [])
        text = (
            f"<!DOCTYPE html>\n"
            f'<html lang="ru">\n'
            f"<head>\n"
            f'<meta charset="UTF-8">\n'
            f'<title>Том {volume} Глава {chapter} — {ch["name"]}</title>\n'
            f"</head>\n"
            f"<body>\n"
            f"<h1>Том {volume} Глава {chapter} — {ch['name']}</h1>\n"
        )
        if isinstance(ch["content"], str):
            # If content is a string, it is likely using old HTML format
            soup = BeautifulSoup(ch["content"], "html.parser")
            for tag in soup.find_all("img"):
                img_filename = tag["src"].split("/")[-1]
                if attachments:
                    attachment = next(
                        (a for a in attachments if a["filename"] == img_filename), None
                    )
                    if attachment:
                        tag["src"] = f"{assets_path.name}/{attachment['filename']}"
            text += str(soup)
        elif isinstance(ch["content"], dict):
            # If content is a dict, it is using the new custom format
            text += self.convert_ranobe_content_to_html(
                ch["content"]["content"], attachments
            )
        text += "\n</body>\n</html>"

        with file.open("w", encoding="utf-8") as f:
            f.write(text)

        tasks = []
        for attachment in attachments:
            img_url = f"{self.resource_base_url}{attachment['url']}"
            img_path = assets_path / attachment["filename"]
            tasks.append(self._download_file(await self.session, img_url, img_path))

        await asyncio.gather(*tasks)

    @staticmethod
    def convert_ranobe_content_to_html(
        content: list[dict], attachments: list[dict], assets_base: str = "assets"
    ) -> str:
        """
        Convert RanobeLib content from custom to HTML format

        :param content: The content in custom format
        :param attachments: Attachments list
        :param assets_base: Base path for assets in the HTML
        :return: The content converted to HTML format
        """
        soup = BeautifulSoup()
        for item in content:
            if item["type"] == "paragraph":
                p = soup.new_tag("p")
                for c in item.get("content", []):
                    if c["type"] == "text":
                        if marks := c.get("marks"):
                            match marks[0]["type"]:
                                case "bold":
                                    b = soup.new_tag("b")
                                    b.string = c["text"]
                                    p.append(b)
                                case "italic":
                                    i = soup.new_tag("i")
                                    i.string = c["text"]
                                    p.append(i)
                                case "underline":
                                    u = soup.new_tag("u")
                                    u.string = c["text"]
                                    p.append(u)
                                case _:
                                    print("Unknown mark type:", marks[0]["type"])
                                    p.append(c["text"])
                        else:
                            p.append(c["text"])
                    if c["type"] == "hardBreak":
                        br = soup.new_tag("br")
                        p.append(br)
                soup.append(p)
            elif item["type"] == "horizontalRule":
                hr = soup.new_tag("hr")
                soup.append(hr)
            elif item["type"] == "image":
                images = item["attrs"].get("images", [])
                for num, image in enumerate(images):
                    img = soup.new_tag("img")
                    img["src"] = f"{assets_base}/{attachments[num]['filename']}"
                    soup.append(img)
        return str(soup)
