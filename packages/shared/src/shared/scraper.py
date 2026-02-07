"""Website scraper using Firecrawl.

Scrapes website URLs to extract content for enriching call context.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("website-scraper")


@dataclass
class ScrapedContent:
    """Result of scraping a website."""

    url: str
    title: str | None = None
    description: str | None = None
    markdown: str | None = None
    success: bool = True
    error: str | None = None


class WebsiteScraper:
    """Scrapes websites using Firecrawl API."""

    def __init__(self, api_key: str | None = None):
        """Initialize the scraper.

        Args:
            api_key: Firecrawl API key. If not provided, reads from FIRECRAWL_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self._client = None

    def _get_client(self):
        """Lazy-load the Firecrawl client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "Firecrawl API key not set. Set FIRECRAWL_API_KEY environment variable."
                )
            try:
                from firecrawl import FirecrawlApp

                self._client = FirecrawlApp(api_key=self.api_key)
            except ImportError as e:
                raise ImportError(
                    "firecrawl-py not installed. Run: uv add firecrawl-py"
                ) from e
        return self._client

    def scrape(self, url: str, timeout: int = 30) -> ScrapedContent:
        """Scrape a website URL.

        Args:
            url: The URL to scrape.
            timeout: Request timeout in seconds.

        Returns:
            ScrapedContent with the scraped data.
        """
        if not url:
            return ScrapedContent(url="", success=False, error="No URL provided")

        # Ensure URL has protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            client = self._get_client()

            logger.info(f"Scraping website: {url}")
            result = client.scrape_url(
                url,
                params={
                    "formats": ["markdown"],
                    "timeout": timeout * 1000,  # Firecrawl uses milliseconds
                },
            )

            # Extract content from result
            markdown = result.get("markdown", "")
            metadata = result.get("metadata", {})
            title = metadata.get("title", "")
            description = metadata.get("description", "")

            logger.info(f"Successfully scraped {url}: {len(markdown)} chars")

            return ScrapedContent(
                url=url,
                title=title,
                description=description,
                markdown=markdown,
                success=True,
            )

        except ValueError as e:
            # API key not set
            logger.warning(f"Scraper not configured: {e}")
            return ScrapedContent(url=url, success=False, error=str(e))

        except ImportError as e:
            # Firecrawl not installed
            logger.warning(f"Firecrawl not installed: {e}")
            return ScrapedContent(url=url, success=False, error=str(e))

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return ScrapedContent(url=url, success=False, error=str(e))

    async def scrape_async(self, url: str, timeout: int = 30) -> ScrapedContent:
        """Scrape a website URL asynchronously.

        Args:
            url: The URL to scrape.
            timeout: Request timeout in seconds.

        Returns:
            ScrapedContent with the scraped data.
        """
        if not url:
            return ScrapedContent(url="", success=False, error="No URL provided")

        # Ensure URL has protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            if not self.api_key:
                raise ValueError(
                    "Firecrawl API key not set. Set FIRECRAWL_API_KEY environment variable."
                )

            from firecrawl import AsyncFirecrawl

            async_client = AsyncFirecrawl(api_key=self.api_key)

            logger.info(f"Scraping website (async): {url}")
            result = await async_client.scrape_url(
                url,
                params={
                    "formats": ["markdown"],
                    "timeout": timeout * 1000,
                },
            )

            markdown = result.get("markdown", "")
            metadata = result.get("metadata", {})
            title = metadata.get("title", "")
            description = metadata.get("description", "")

            logger.info(f"Successfully scraped {url}: {len(markdown)} chars")

            return ScrapedContent(
                url=url,
                title=title,
                description=description,
                markdown=markdown,
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return ScrapedContent(url=url, success=False, error=str(e))


def summarize_website_content(content: ScrapedContent, max_chars: int = 2000) -> str:
    """Summarize scraped website content for use in agent context.

    Args:
        content: The scraped content.
        max_chars: Maximum characters to include.

    Returns:
        A summarized string suitable for agent context.
    """
    if not content.success or not content.markdown:
        return ""

    parts = []

    if content.title:
        parts.append(f"Company: {content.title}")

    if content.description:
        parts.append(f"Description: {content.description}")

    # Include truncated markdown content
    markdown = content.markdown.strip()
    if markdown:
        # Remove excessive whitespace
        import re

        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        markdown = re.sub(r" {2,}", " ", markdown)

        # Truncate if needed
        remaining_chars = max_chars - len("\n".join(parts)) - 50
        if len(markdown) > remaining_chars:
            markdown = markdown[:remaining_chars] + "..."

        parts.append(f"Website Content:\n{markdown}")

    return "\n\n".join(parts)


# Convenience function
def scrape_website(url: str, api_key: str | None = None) -> ScrapedContent:
    """Scrape a website URL.

    Args:
        url: The URL to scrape.
        api_key: Optional Firecrawl API key.

    Returns:
        ScrapedContent with the scraped data.
    """
    scraper = WebsiteScraper(api_key=api_key)
    return scraper.scrape(url)
