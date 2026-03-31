"""
Huaban crawler.

This integration avoids scraping Huaban's protected HTML pages directly.
Instead it uses Huaban's public JSON APIs for pins / boards / discovery feeds
and converts the returned file key into a stable raw image host URL.
"""
import asyncio
import logging
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import aiohttp

from utils.image_validator import ImageValidator


class HuabanCrawler:
    """Crawler for publicly accessible Huaban pins and feeds."""

    API_ROOT = "https://api.huaban.com"
    RAW_IMAGE_HOST = "https://hbimg.huabanimg.com"
    DEFAULT_LIST_LIMIT = 24
    MAX_LIST_LIMIT = 48

    def __init__(self):
        self.validator = ImageValidator()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://huaban.com/",
            "Origin": "https://huaban.com",
            "Cache-Control": "no-cache",
        }

    async def extract_image(
        self,
        url: str,
        extracted_params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Extract Huaban material URLs from a supported Huaban page."""
        del extracted_params

        session = None
        try:
            link_type = self._classify_link(url)
            logging.info(f"🌸 Start Huaban extraction: {url}")
            logging.info(f"🔎 Huaban link type: {link_type}")

            session = await self._create_session()

            if link_type == "pin":
                return await self._extract_pin(session, url)
            if link_type == "board":
                return await self._extract_board(session, url)
            if link_type == "discovery":
                return await self._extract_discovery(session, url)

            logging.info("⚠️ Unsupported Huaban URL shape for this crawler")
            return None

        except Exception as error:
            logging.error(f"❌ Huaban extraction failed: {error}")
            return None
        finally:
            if session:
                await session.close()

    async def _create_session(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        return aiohttp.ClientSession(connector=connector, timeout=timeout, headers=self.headers)

    def _classify_link(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        path = (parsed.path or "").rstrip("/").lower()

        if "api.huaban.com" in hostname:
            if path.startswith("/pins/"):
                return "pin"
            if path.startswith("/boards/"):
                return "board"
            if path.startswith("/discovery"):
                return "discovery"

        if "huaban.com" in hostname:
            if path.startswith("/pins/"):
                return "pin"
            if path.startswith("/boards/"):
                return "board"
            if path in {"", "/discovery"} or path.startswith("/discovery/"):
                return "discovery"

        return "unknown"

    async def _extract_pin(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        pin_id = self._extract_numeric_id(url, "pins")
        if not pin_id:
            return None

        data = await self._get_json(session, f"{self.API_ROOT}/pins/{pin_id}")
        pin = data.get("pin") if isinstance(data, dict) else None
        if not isinstance(pin, dict):
            return None

        entry = self._build_pin_entry(pin)
        if not entry:
            return None

        if not await self.validator.validate_image_url(entry["imageUrl"]):
            return None

        if entry.get("previewOnly"):
            return self._build_preview_image_result(
                [entry],
                original_url=url,
                link_type="pin",
                source="huaban-pin-api",
                method="pin_api_preview_image",
                reason=entry["previewOnlyReason"],
            )

        return {
            "imageUrl": entry["imageUrl"],
            "imageUrls": [entry["imageUrl"]],
            "pages": [{"page": 1, "imageUrl": entry["imageUrl"]}],
            "pageCount": 1,
            "isMultiPage": False,
            "platform": "Huaban",
            "source": "huaban-pin-api",
            "method": "pin_api",
            "linkType": "pin",
            "pinId": entry["pinId"],
            "title": entry["title"],
            "tags": entry["tags"],
            "boardTitle": entry["boardTitle"],
            "original_url": url,
        }

    async def _extract_board(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        board_id = self._extract_numeric_id(url, "boards")
        if not board_id:
            return None

        board_meta = await self._get_json(session, f"{self.API_ROOT}/boards/{board_id}")
        pins_payload = await self._get_json(
            session,
            f"{self.API_ROOT}/boards/{board_id}/pins",
            params=self._forward_list_params(url),
        )

        pins = self._extract_pins_from_payload(pins_payload)
        result = await self._build_feed_result(
            pins,
            url,
            link_type="board",
            source="huaban-board-api",
            method="board_pins_api",
        )
        if not result:
            return None

        board = board_meta.get("board") if isinstance(board_meta, dict) else None
        if isinstance(board, dict):
            result["boardId"] = board_id
            result["boardTitle"] = board.get("title")

        return result

    async def _extract_discovery(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        discovery_path = self._build_discovery_api_path(url)
        data = await self._get_json(session, discovery_path, params=self._forward_list_params(url))
        pins = self._extract_pins_from_payload(data)
        return await self._build_feed_result(
            pins,
            url,
            link_type="discovery",
            source="huaban-discovery-api",
            method="discovery_api",
        )

    async def _get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                raise RuntimeError(f"Huaban API request failed: HTTP {response.status} for {response.url}")
            return await response.json(content_type=None)

    def _extract_numeric_id(self, url: str, segment: str) -> Optional[str]:
        path = (urlparse(url).path or "").strip("/")
        parts = [part for part in path.split("/") if part]
        for index, part in enumerate(parts[:-1]):
            if part.lower() == segment and parts[index + 1].isdigit():
                return parts[index + 1]
        return None

    def _build_discovery_api_path(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        path = (parsed.path or "").rstrip("/")

        if "api.huaban.com" in hostname and path:
            return f"{self.API_ROOT}{path}"

        normalized_path = path or "/discovery"
        if not normalized_path.startswith("/discovery"):
            normalized_path = "/discovery"

        return f"{self.API_ROOT}{normalized_path}"

    def _forward_list_params(self, url: str) -> Dict[str, str]:
        params = parse_qs(urlparse(url).query, keep_blank_values=False)
        forwarded: Dict[str, str] = {}

        for key in ["max", "limit", "wfl", "category", "sort"]:
            values = params.get(key)
            if not values:
                continue
            forwarded[key] = values[0]

        limit_value = forwarded.get("limit")
        if not limit_value:
            forwarded["limit"] = str(self.DEFAULT_LIST_LIMIT)
            return forwarded

        try:
            parsed_limit = max(1, min(int(limit_value), self.MAX_LIST_LIMIT))
        except ValueError:
            parsed_limit = self.DEFAULT_LIST_LIMIT

        forwarded["limit"] = str(parsed_limit)
        return forwarded

    def _extract_pins_from_payload(self, data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, dict):
            return []

        if isinstance(data.get("pin"), dict):
            return [data["pin"]]

        pins = data.get("pins")
        if isinstance(pins, list):
            return [pin for pin in pins if isinstance(pin, dict)]

        board = data.get("board")
        board_pins = board.get("pins") if isinstance(board, dict) else None
        if isinstance(board_pins, list):
            return [pin for pin in board_pins if isinstance(pin, dict)]

        return []

    def _build_pin_entry(self, pin: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        image_url = self._normalize_pin_image_url(pin)
        if not image_url:
            return None

        board = pin.get("board") if isinstance(pin.get("board"), dict) else {}
        tags = pin.get("tags")
        if not isinstance(tags, list):
            text_meta = pin.get("text_meta") if isinstance(pin.get("text_meta"), dict) else {}
            tags = text_meta.get("tags") if isinstance(text_meta.get("tags"), list) else []

        return {
            "pinId": pin.get("pin_id"),
            "imageUrl": image_url,
            "title": str(pin.get("raw_text") or "").strip(),
            "tags": [tag for tag in tags if isinstance(tag, str)],
            "boardTitle": board.get("title"),
            "previewOnly": self._is_public_preview_only_pin(pin),
            "previewOnlyReason": self._build_preview_only_reason(pin),
        }

    def _is_public_preview_only_pin(self, pin: Dict[str, Any]) -> bool:
        file_material = pin.get("file_material") if isinstance(pin.get("file_material"), dict) else {}
        extra = pin.get("extra") if isinstance(pin.get("extra"), dict) else {}

        has_material_id = extra.get("material_id") is not None or file_material.get("material_id") is not None
        source_type = str(file_material.get("source_type") or "").strip().lower()
        has_external_source = bool(pin.get("source") or pin.get("link") or pin.get("original"))

        return bool(has_material_id and source_type == "produced" and not has_external_source)

    def _build_preview_only_reason(self, pin: Dict[str, Any]) -> str:
        if not self._is_public_preview_only_pin(pin):
            return ""

        file_material = pin.get("file_material") if isinstance(pin.get("file_material"), dict) else {}
        material_type = str(file_material.get("material_type") or "源素材").upper()
        return (
            f"该花瓣素材公开接口仅返回带水印预览图，未暴露公开无水印{material_type}下载字段；"
            "如需原素材，通常需要在花瓣站内登录有权限的账号后下载。"
        )

    def _build_preview_image_warning_text(self) -> str:
        """Short user-facing warning when only the public preview image is available."""
        return "已提取公开预览图，可直接下载，但可能包含平台水印，未获取到无水印原素材"

    def _normalize_pin_image_url(self, pin: Dict[str, Any]) -> Optional[str]:
        file_info = pin.get("file") if isinstance(pin.get("file"), dict) else {}
        file_key = str(file_info.get("key") or "").strip().lstrip("/")
        if file_key:
            return f"{self.RAW_IMAGE_HOST}/{file_key}"

        raw_url = str(file_info.get("url") or "").strip()
        if not raw_url:
            return None

        parsed = urlparse(raw_url)
        raw_path = (parsed.path or "").strip("/")
        if not raw_path:
            return None

        return f"{self.RAW_IMAGE_HOST}/{raw_path}"

    async def _build_feed_result(
        self,
        pins: List[Dict[str, Any]],
        original_url: str,
        link_type: str,
        source: str,
        method: str
    ) -> Optional[Dict]:
        limit = self._forward_list_params(original_url).get("limit")
        max_items = self.DEFAULT_LIST_LIMIT
        if limit and limit.isdigit():
            max_items = max(1, min(int(limit), self.MAX_LIST_LIMIT))

        entries = []
        seen_urls = set()
        for pin in pins:
            entry = self._build_pin_entry(pin)
            if not entry:
                continue
            if entry["imageUrl"] in seen_urls:
                continue
            seen_urls.add(entry["imageUrl"])
            entries.append(entry)
            if len(entries) >= max_items:
                break

        if not entries:
            return None

        preview_only_entries = [entry for entry in entries if entry.get("previewOnly")]
        entries = [entry for entry in entries if not entry.get("previewOnly")]

        if not entries:
            if preview_only_entries:
                validated_preview_entries = await self._filter_valid_entries(preview_only_entries)
                if validated_preview_entries:
                    return self._build_preview_image_result(
                        validated_preview_entries,
                        original_url=original_url,
                        link_type=link_type,
                        source=source,
                        method=f"{method}_preview_image",
                        reason=preview_only_entries[0]["previewOnlyReason"],
                    )
                return self._build_preview_only_result(
                    original_url,
                    link_type=link_type,
                    source=source,
                    method=f"{method}_preview_only",
                    reason=preview_only_entries[0]["previewOnlyReason"],
                )
            return None

        validated_entries = await self._filter_valid_entries(entries)
        if not validated_entries:
            return None

        image_urls = [entry["imageUrl"] for entry in validated_entries]
        return {
            "imageUrl": image_urls[0],
            "imageUrls": image_urls,
            "pages": [
                {
                    "page": index + 1,
                    "imageUrl": entry["imageUrl"],
                    "pinId": entry["pinId"],
                    "title": entry["title"],
                }
                for index, entry in enumerate(validated_entries)
            ],
            "pageCount": len(image_urls),
            "isMultiPage": len(image_urls) > 1,
            "pins": validated_entries,
            "platform": "Huaban",
            "source": source,
            "method": method,
            "linkType": link_type,
            "original_url": original_url,
        }

    def _build_preview_only_result(
        self,
        original_url: str,
        link_type: str,
        source: str,
        method: str,
        reason: str
    ) -> Dict[str, Any]:
        return {
            "status": "preview_only",
            "error": reason,
            "warningText": "公开接口仅提供带水印预览图，未返回无水印原素材下载地址",
            "platform": "Huaban",
            "source": source,
            "method": method,
            "linkType": link_type,
            "original_url": original_url,
        }

    def _build_preview_image_result(
        self,
        entries: List[Dict[str, Any]],
        original_url: str,
        link_type: str,
        source: str,
        method: str,
        reason: str
    ) -> Dict[str, Any]:
        image_urls = [entry["imageUrl"] for entry in entries]
        return {
            "status": "preview_image",
            "error": reason,
            "warningText": self._build_preview_image_warning_text(),
            "imageUrl": image_urls[0],
            "imageUrls": image_urls,
            "pages": [
                {
                    "page": index + 1,
                    "imageUrl": entry["imageUrl"],
                    "pinId": entry.get("pinId"),
                    "title": entry.get("title"),
                }
                for index, entry in enumerate(entries)
            ],
            "pageCount": len(image_urls),
            "isMultiPage": len(image_urls) > 1,
            "platform": "Huaban",
            "source": source,
            "method": method,
            "linkType": link_type,
            "original_url": original_url,
        }

    async def _filter_valid_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        async def validate_entry(entry: Dict[str, Any]) -> bool:
            return await self.validator.validate_image_url(entry["imageUrl"])

        validation_tasks = [asyncio.create_task(validate_entry(entry)) for entry in entries]
        try:
            validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        finally:
            for task in validation_tasks:
                if not task.done():
                    task.cancel()
            if validation_tasks:
                await asyncio.gather(*validation_tasks, return_exceptions=True)

        valid_entries = []
        for entry, result in zip(entries, validation_results):
            if result is True:
                valid_entries.append(entry)

        return valid_entries

    async def close(self):
        if self.validator:
            await self.validator.close()
