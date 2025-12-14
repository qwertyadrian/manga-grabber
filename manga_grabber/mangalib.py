import asyncio
import logging
import re
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

from .base import BaseGrabber, register_grabber
from .exceptions import ChapterInfoError, GrabberException, TitleNotFoundError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@register_grabber("mangalib.me")
class MangaLib(BaseGrabber):
    """A class to interact with the MangaLib API and download manga chapters"""

    api_base_url: str = "https://api.cdnlibs.org/api"
    resource_base_url: str = "https://img2.imglib.info"

    def __init__(self, title_url: str, token: str | None = None):
        super().__init__(title_url, token)
        self._headers["Referer"] = "https://mangalib.me/"
        if token is not None:
            self._headers["Authorization"] = f"Bearer {token}"
        self.manga_id = int(re.findall(r"/(\d+)--?([\w-]*)", title_url)[0][0])
        self.manga_name = re.findall(r"/(\d+)--?([\w-]*)", title_url)[0][1]

    async def get_chapters(self) -> list:
        """Fetch the list of chapters and additional info for the manga"""
        session = await self.session
        async with session.get(
            f"{self.api_base_url}/manga/{self.manga_id}--{self.manga_name}/chapters"
        ) as response:
            match response.status:
                case 404:
                    raise TitleNotFoundError(f"Title {self.manga_name} not found")
                case 200:
                    return (await response.json())["data"]
                case _:
                    raise GrabberException(
                        f"Failed to fetch chapters: {response.status}"
                    )

    async def get_chapter_info(
        self, chapter: int, volume: int, branch_id: int = 0
    ) -> dict:
        """
        Fetch detailed information about a specific chapter of the manga

        :param chapter: Chapter number
        :param volume: Volume number
        :param branch_id: ID of translation branch (optional, for multi-branch titles).
        If the specified translation branch for the chapter is not found, the function returns another available branch.
        """
        session = await self.session
        params = {"number": chapter, "volume": volume}
        if branch_id > 0:
            params["branch_id"] = branch_id
        async with session.get(
            f"{self.api_base_url}/manga/{self.manga_id}--{self.manga_name}/chapter",
            params=params,
        ) as response:
            match response.status:
                case 404:
                    raise ChapterInfoError(
                        f"Info for chapter {chapter} volume {volume} not found"
                    )
                case 200:
                    return (await response.json())["data"]
                case _:
                    raise GrabberException(
                        f"Failed to fetch chapter info: {response.status}"
                    )

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


@register_grabber("hentailib.me")
class HentaiLib(MangaLib):
    api_base_url: str = "https://hapi.hentaicdn.org/api"
    resource_base_url = "https://img2h.hentaicdn.org"

    def __init__(self, title_url: str, token: str | None = None):
        super().__init__(title_url, token)
        self._headers["Referer"] = "https://hentailib.me/"


@register_grabber("ranobelib.me")
class RanobeLib(MangaLib):
    resource_base_url = "https://ranobelib.me"
    url_regex = re.compile(
        r"https?://(www\.)?[-a-zA-Zа-яA-Я0-9@:%._+~#=]{1,256}\.[a-zA-Zа-яA-Я0-9]{1,6}\b([-a-zA-Zа-яA-Я0-9()@:%_+.~#?&/=]*)"
    )

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
        :param branch_id: ID of translation branch (optional, for multi-branch titles)
        :param prefix: Prefix for the downloaded files
        """
        ch = await self.get_chapter_info(chapter, volume, branch_id)

        output_dir.mkdir(parents=True, exist_ok=True)

        file = output_dir / f"{prefix}index.html"
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
            logger.info("Content is in old HTML format")
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
        # Replace URLs in the text with links
        soup = BeautifulSoup(text, "html.parser")
        for element in soup.find_all(string=True):
            if element.parent.name != "a":
                new_text = re.sub(self.url_regex, self._create_hyperlink, str(element))
                if new_text != str(element):
                    element.replace_with(BeautifulSoup(new_text, "html.parser"))
        text = str(soup)

        file.write_text(text, encoding="utf-8")

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
                                    logger.warning(
                                        "Unknown mark type: %s", marks[0]["type"]
                                    )
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
                for attachment in attachments:
                    for image in images:
                        if attachment["name"] == image["image"]:
                            img = soup.new_tag("img")
                            img["src"] = f"{assets_base}/{attachment['filename']}"
                            soup.append(img)
        return str(soup)

    @staticmethod
    def _create_hyperlink(match: re.Match) -> str:
        """
        Create a hyperlink HTML tag from a regex match object

        :param match: Regex match object containing the URL
        :return: HTML hyperlink tag
        """
        url = match.group(0)
        parsed_url = urllib.parse.urlparse(url)
        parsed_url = parsed_url._replace(path=urllib.parse.quote(parsed_url.path))
        return f'<a href="{parsed_url.geturl()}" target="_blank">{url}</a>'
