import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Registered parsers for different hostnames
GRABBER_REGISTRY = {}


def register_grabber(hostname):
    """Decorator for registering parser classes for specific hostnames"""

    def decorator(cls):
        GRABBER_REGISTRY[hostname] = cls
        return cls

    return decorator


class BaseGrabber(ABC):
    """Base class for grabbers"""

    def __init__(self, title_url: str, token: str | None = None):
        """
        :param title_url: URL of the title to be grabbed
        :param token: Optional API token for authenticated requests
        """
        self._session: aiohttp.ClientSession | None = None
        self._connector = aiohttp.TCPConnector(limit=20)
        self._token = token
        self._headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0"
        }
        self.title_url = title_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @property
    async def session(self) -> aiohttp.ClientSession:
        """Get the aiohttp session, creating it if it doesn't exist or is closed"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                connector=self._connector,
                middlewares=[self._retry_middleware],
            )
        return self._session

    async def close(self):
        """Close the aiohttp session if it exists and is not closed"""
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    async def _retry_middleware(
        req: aiohttp.ClientRequest, handler: aiohttp.ClientHandlerType
    ) -> aiohttp.ClientResponse:
        """Middleware to retry requests on certain HTTP status codes"""
        max_retries = 5
        for attempt in range(max_retries):
            response = await handler(req)
            match response.status:
                case 429:
                    logger.warning(
                        f"Rate limited. Retrying {attempt + 1}/{max_retries}..."
                    )
                case 500 | 502 | 503 | 504:
                    logger.warning(
                        f"Server error {response.status}. Retrying {attempt + 1}/{max_retries}..."
                    )
                case _:
                    return response
            await asyncio.sleep(2**attempt)
        return response

    @staticmethod
    async def _download_file(
        session: aiohttp.ClientSession, url: str, path: Path, force: bool = False
    ):
        """
        Download a file from the given URL and save it to the specified path

        :param session: aiohttp session to use for the request
        :param url: URL of the file to download
        :param path: Path where the file will be saved
        :param force: If True, overwrite the file if it already exists
        """
        if path.exists() and not force:
            logger.info(f"File {path.name} already exists")
            return
        async with session.get(url) as response:
            response.raise_for_status()
            with path.open("wb") as fd:
                async for chunk in response.content.iter_chunked(1024):
                    fd.write(chunk)

    @abstractmethod
    async def get_chapters(self) -> list:
        """Fetch the list of chapters and additional info for the title"""
        pass

    @abstractmethod
    async def download_chapter(
        self,
        chapter: int | float,
        volume: int,
        output_dir: Path,
        branch_id: int = 0,
        prefix: str = "",
    ):
        """
        Download specific chapter

        :param chapter: Chapter number to download
        :param volume: Volume number of the chapter
        :param output_dir: Directory where the chapter will be saved
        :param branch_id: Optional branch ID for titles with multiple branches
        :param prefix: Optional prefix for the saved files
        """
        pass
