"""
Pixabay API integration for fetching images and videos based on script keywords.

This module provides functionality to search and retrieve media assets from Pixabay
for use in AI video generation. It supports both image and video search with
configurable parameters and proper error handling.
"""

import os
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import aiohttp
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MediaType(Enum):
    """Enumeration for supported media types."""
    IMAGE = "image"
    VIDEO = "video"


class MediaOrientation(Enum):
    """Enumeration for media orientation options."""
    ALL = "all"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass
class MediaResult:
    """Data class representing a single media result from Pixabay."""
    id: int
    type: MediaType
    url: str
    preview_url: str
    tags: List[str]
    width: int
    height: int
    user: str
    page_url: str
    
    # Image-specific fields
    image_url: Optional[str] = None
    large_image_url: Optional[str] = None
    
    # Video-specific fields
    video_url: Optional[str] = None
    video_duration: Optional[float] = None
    video_size: Optional[int] = None


@dataclass
class MediaSearchResult:
    """Data class for search results containing multiple media items."""
    total: int
    total_hits: int
    results: List[MediaResult] = field(default_factory=list)


class PixabayAPIError(Exception):
    """Custom exception for Pixabay API errors."""
    pass


class PixabayClient:
    """
    Client for interacting with the Pixabay API.
    
    Handles authentication, request building, and response parsing
    for both image and video searches.
    """
    
    BASE_URL = "https://pixabay.com/api"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Pixabay client.
        
        Args:
            api_key: Pixabay API key. If not provided, reads from PIXABAY_API_KEY env variable.
        
        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.getenv("PIXABAY_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Pixabay API key is required. Set PIXABAY_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure an aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def search_images(
        self,
        query: str,
        per_page: int = 20,
        page: int = 1,
        orientation: MediaOrientation = MediaOrientation.ALL,
        min_width: int = 0,
        min_height: int = 0,
        safesearch: bool = True,
        category: Optional[str] = None,
        editors_choice: bool = False
    ) -> MediaSearchResult:
        """
        Search for images on Pixabay.
        
        Args:
            query: Search query string.
            per_page: Number of results per page (max 200).
            page: Page number to retrieve.
            orientation: Image orientation filter.
            min_width: Minimum image width.
            min_height: Minimum image height.
            safesearch: Enable safe search filtering.
            category: Image category filter.
            editors_choice: Filter for editor's choice images only.
        
        Returns:
            MediaSearchResult containing matching images.
        
        Raises:
            PixabayAPIError: If the API request fails.
        """
        params = {
            "key": self.api_key,
            "q": query,
            "image_type": "photo",
            "per_page": min(per_page, 200),
            "page": page,
            "orientation": orientation.value,
            "min_width": min_width,
            "min_height": min_height,
            "safesearch": str(safesearch).lower(),
        }
        
        if category:
            params["category"] = category
        if editors_choice:
            params["editors_choice"] = "true"
        
        return await self._make_request("", params, MediaType.IMAGE)
    
    async def search_videos(
        self,
        query: str,
        per_page: int = 20,
        page: int = 1,
        orientation: MediaOrientation = MediaOrientation.ALL,
        min_width: int = 0,
        min_height: int = 0,
        safesearch: bool = True,
        video_type: str = "all"
    ) -> MediaSearchResult:
        """
        Search for videos on Pixabay.
        
        Args:
            query: Search query string.
            per_page: Number of results per page (max 200).
            page: Page number to retrieve.
            orientation: Video orientation filter.
            min_width: Minimum video width.
            min_height: Minimum video height.
            safesearch: Enable safe search filtering.
            video_type: Type of video (all, film, animation).
        
        Returns:
            MediaSearchResult containing matching videos.
        
        Raises:
            PixabayAPIError: If the API request fails.
        """
        params = {
            "key": self.api_key,
            "q": query,
            "video_type": video_type,
            "per_page": min(per_page, 200),
            "page": page,
            "orientation": orientation.value,
            "min_width": min_width,
            "min_height": min_height,
            "safesearch": str(safesearch).lower(),
        }
        
        return await self._make_request("/videos", params, MediaType.VIDEO)
    
    async def _make_request(
        self,
        endpoint: str,
        params: Dict[str, Any],
        media_type: MediaType
    ) -> MediaSearchResult:
        """
        Make an API request to Pixabay.
        
        Args:
            endpoint: API endpoint (empty for images, '/videos' for videos).
            params: Query parameters for the request.
            media_type: Type of media being requested.
        
        Returns:
            MediaSearchResult parsed from the API response.
        
        Raises:
            PixabayAPIError: If the request fails or returns an error.
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            session = await self._ensure_session()
            
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise PixabayAPIError(
                        f"Pixabay API returned status {response.status}: {error_text}"
                    )
                
                data = await response.json()
                
                if data.get("total") == 0:
                    return MediaSearchResult(total=0, total_hits=0, results=[])
                
                results = self._parse_response(data, media_type)
                
                return MediaSearchResult(
                    total=data.get("total", 0),
                    total_hits=data.get("totalHits", 0),
                    results=results
                )
                
        except asyncio.TimeoutError:
            raise PixabayAPIError("Pixabay API request timed out")
        except aiohttp.ClientError as e:
            raise PixabayAPIError(f"Pixabay API request failed: {str(e)}")
    
    def _parse_response(
        self,
        data: Dict[str, Any],
        media_type: MediaType
    ) -> List[MediaResult]:
        """
        Parse the API response into MediaResult objects.
        
        Args:
            data: Raw API response data.
            media_type: Type of media being parsed.
        
        Returns:
            List of MediaResult objects.
        """
        results = []
        hits = data.get("hits", [])
        
        for hit in hits:
            try:
                if media_type == MediaType.IMAGE:
                    result = self._parse_image_hit(hit)
                else:
                    result = self._parse_video_hit(hit)
                results.append(result)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse media hit: {e}")
                continue
        
        return results
    
    def _parse_image_hit(self, hit: Dict[str, Any]) -> MediaResult:
        """
        Parse an image hit from the API response.
        
        Args:
            hit: Raw image data from API.
        
        Returns:
            MediaResult for the image.
        """
        return MediaResult(
            id=hit["id"],
            type=MediaType.IMAGE,
            url=hit.get("pageURL", ""),
            preview_url=hit.get("previewURL", ""),
            tags=hit.get("tags", "").split(", ") if hit.get("tags") else [],
            width=hit.get("imageWidth", 0),
            height=hit.get("imageHeight", 0),
            user=hit.get("user", ""),
            page_url=hit.get("pageURL", ""),
            image_url=hit.get("webformatURL", ""),
            large_image_url=hit.get("largeImageURL", "")
        )
    
    def _parse_video_hit(self, hit: Dict[str, Any]) -> MediaResult:
        """
        Parse a video hit from the API response.
        
        Args:
            hit: Raw video data from API.
        
        Returns:
            MediaResult for the video.
        """
        videos = hit.get("videos", {})
        
        # Prefer the largest available video quality
        video_url = ""
        video_size = 0
        
        for quality in ["large", "medium", "small", "tiny"]:
            if quality in videos:
                video_data = videos[quality]
                if video_data.get("url") and video_data.get("size", 0) > video_size:
                    video_url = video_data["url"]
                    video_size = video_data.get("size", 0)
        
        return MediaResult(
            id=hit["id"],
            type=MediaType.VIDEO,
            url=hit.get("pageURL", ""),
            preview_url=hit.get("pageURL", ""),  # Videos don't have preview URLs
            tags=hit.get("tags", "").split(", ") if hit.get("tags") else [],
            width=hit.get("videoWidth", 0),
            height=hit.get("videoHeight", 0),
            user=hit.get("user", ""),
            page_url=hit.get("pageURL", ""),
            video_url=video_url,
            video_duration=hit.get("duration", 0),
            video_size=video_size
        )


async def fetch_media_for_keywords(
    keywords: List[str],
    media_type: MediaType = MediaType.VIDEO,
    items_per_keyword: int = 3,
    api_key: Optional[str] = None
) -> Dict[str, List[MediaResult]]:
    """
    Fetch media for a list of keywords from Pixabay.
    
    This is a high-level function that searches for media matching each keyword
    and returns organized results.
    
    Args:
        keywords: List of search keywords/phrases.
        media_type: Type of media to search for (image or video).
        items_per_keyword: Number of media items to fetch per keyword.
        api_key: Optional Pixabay API key.
    
    Returns:
        Dictionary mapping keywords to lists of MediaResult objects.
    
    Raises:
        PixabayAPIError: If API requests fail.
    """
    async with PixabayClient(api_key) as client:
        results = {}
        
        for keyword in keywords:
            try:
                if media_type == MediaType.IMAGE:
                    search_result = await client.search_images(
                        query=keyword,
                        per_page=items_per_keyword,
                        safesearch=True
                    )
                else:
                    search_result = await client.search_videos(
                        query=keyword,
                        per_page=items_per_keyword,
                        safesearch=True
                    )
                
                results[keyword] = search_result.results[:items_per_keyword]
                
                if not search_result.results:
                    logger.info(f"No results found for keyword: {keyword}")
                else:
                    logger.info(
                        f"Found {len(search_result.results)} results for keyword: {keyword}"
                    )
                    
            except PixabayAPIError as e:
                logger.error(f"Failed to fetch media for keyword '{keyword}': {e}")
                results[keyword] = []
                continue
        
        return results


async def download_media(
    media_result: MediaResult,
    output_path: str,
    session: Optional[aiohttp.ClientSession] = None
) -> bool:
    """
    Download a media file from Pixabay.
    
    Args:
        media_result: MediaResult object containing the media URL.
        output_path: Path where the media file should be saved.
        session: Optional aiohttp session for reuse.
    
    Returns:
        True if download was successful, False otherwise.
    """
    url = media_result.video_url or media_result.image_url
    if not url:
        logger.error(f"No download URL available for media ID: {media_result.id}")
        return False
    
    try:
        if session is None:
            async with aiohttp.ClientSession() as temp_session:
                return await _download_file(temp_session, url, output_path)
        else:
            return await _download_file(session, url, output_path)
            
    except Exception as e:
        logger.error(f"Failed to download media from {url}: {e}")
        return False


async def _download_file(
    session: aiohttp.ClientSession,
    url: str,
    output_path: str
) -> bool:
    """
    Download a file from a URL and save it locally.
    
    Args:
        session: aiohttp session for making requests.
        url: URL of the file to download.
        output_path: Local path to save the file.
    
    Returns:
        True if download was successful, False otherwise.
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
            if response.status != 200:
                logger.error(f"Download failed with status {response.status}")
                return False
            
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            
            with open(output_path, "wb") as f:
                while True:
                    chunk = await response.content.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
            
            logger.info(f"Successfully downloaded media to {output_path}")
            return True
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False


# Convenience function for getting media URLs from script keywords
async def get_media_urls_for_script(
    script_keywords: List[str],
    media_type: MediaType = MediaType.VIDEO,
    max_per_keyword: int = 3
) -> Dict[str, List[str]]:
    """
    Get media URLs for a list of script keywords.
    
    This is a simplified interface that returns only URLs for easy integration.
    
    Args:
        script_keywords: List of keywords from the script.
        media_type: Type of media to search for.
        max_per_keyword: Maximum number of URLs per keyword.
    
    Returns:
        Dictionary mapping keywords to lists of media URLs.
    """
    media_dict = await fetch_media_for_keywords(
        keywords=script_keywords,
        media_type=media_type,
        items_per_keyword=max_per_keyword
    )
    
    url_dict = {}
    for keyword, results in media_dict.items():
        urls = []
        for result in results:
            url = result.video_url or result.image_url
            if url:
                urls.append(url)
        url_dict[keyword] = urls
    
    return url_dict