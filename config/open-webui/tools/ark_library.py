"""
title: Ark Reference Library
author: The Ark
description: Search and read the Ark's offline Reference Library (Kiwix): Wikipedia, WikiMed, iFixit, Stack Exchange (mechanics, DIY, electronics, gardening...), LibreTexts, survival guides and more. Works fully offline.
version: 1.0
requirements:
"""

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, Field


class _TextExtractor(HTMLParser):
    """Turn an article's HTML into plain text, keeping headings, list items and table rows readable."""

    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "dd", "dt", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
            if tag in ("h1", "h2", "h3", "h4"):
                self.out.append("## ")
            elif tag == "li":
                self.out.append("- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def text(self):
        lines = []
        for line in "".join(self.out).splitlines():
            line = re.sub(r"[ \t\xa0]+", " ", line).strip(" |")
            if line in ("", "-", "##", "## "):
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            if lines and lines[-1] in ("-", "##") :
                lines[-1] += " " + line
            else:
                lines.append(line)
        return "\n".join(lines).strip()


class Tools:
    class Valves(BaseModel):
        KIWIX_URL: str = Field(default="http://kiwix:8080", description="Kiwix address as seen from Open WebUI (inside Docker).")
        PUBLIC_URL: str = Field(default="http://ark.local:8080", description="Kiwix address people's browsers use, for source links.")
        MAX_RESULTS: int = Field(default=8, description="Search results returned to the model.")
        MAX_ARTICLE_CHARS: int = Field(default=12000, description="Longest article text passed to the model (about 3,000 tokens).")

    def __init__(self):
        self.valves = self.Valves()
        self._books = None

    # ---------- helpers ----------
    def _get(self, path: str, timeout: int = 30) -> bytes:
        with urllib.request.urlopen(self.valves.KIWIX_URL.rstrip("/") + path, timeout=timeout) as r:
            return r.read()

    def _catalog(self) -> list:
        """[(id, title, name)] for every collection, e.g. ('ifixit_en_all_2025-12', 'iFixit in English', 'ifixit_en_all')."""
        if self._books is None:
            root = ET.fromstring(self._get("/catalog/v2/entries?count=500"))
            ns = {"a": "http://www.w3.org/2005/Atom"}
            books = []
            for e in root.findall("a:entry", ns):
                title = (e.findtext("a:title", "", ns) or "").strip()
                name = (e.findtext("a:name", "", ns) or "").strip()
                book_id = ""
                for link in e.findall("a:link", ns):
                    if link.get("type") == "text/html" and link.get("href", "").startswith("/content/"):
                        book_id = link.get("href").split("/content/", 1)[1].strip("/")
                if book_id:
                    books.append((book_id, title, name))
            self._books = books
        return self._books

    def _match_collection(self, collection: str) -> list:
        c = collection.strip().lower()
        if not c:
            return []
        aliases = {"wikimed": "medicine", "medical": "medicine", "mechanic": "mechanics", "repair": "ifixit", "wiki": "wikipedia_en_all"}
        c = aliases.get(c, c)
        return [b for b in self._catalog() if c in b[0].lower() or c in b[1].lower()]

    async def _status(self, emitter, text: str, done: bool = False):
        if emitter:
            await emitter({"type": "status", "data": {"description": text, "done": done}})

    # ---------- tools the model can call ----------
    async def list_collections(self) -> str:
        """
        List every collection in the Ark's offline Reference Library (titles and ids).
        Use this to pick a collection to search, for example iFixit for repair guides or WikiMed for medicine.
        """
        return "\n".join(f"- {title}  (collection: {book_id})" for book_id, title, _ in self._catalog())

    async def search_library(
        self,
        query: str,
        collection: str = "",
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> str:
        """
        Search the Ark's offline Reference Library: Wikipedia, WikiMed (medicine), iFixit repair guides,
        Stack Exchange Q&A (Motor Vehicle Mechanics, Home Improvement/DIY, Electrical Engineering, Gardening,
        Cooking, Ham Radio, The Great Outdoors, Medical Sciences...), LibreTexts textbooks, Wikibooks,
        Wikivoyage, survival, water, food and first-aid guides.
        Use short keyword queries (e.g. "F-150 front brake pads", "diesel injector bleeding", "tick bite").
        Returns titles, the collection each came from, a snippet and a link to pass to read_article.
        :param query: Keywords to search for.
        :param collection: Optional part of a collection name or title to search only that one, e.g. "ifixit", "mechanics", "medicine", "diy", "wikipedia", "gardening". Leave empty to search everything.
        """
        await self._status(__event_emitter__, f"Searching the library for “{query}”…")
        scoped = self._match_collection(collection) if collection else []
        words, used, items = query.split(), query, []
        # Kiwix only returns pages containing every word, so widen the search by dropping words from the end.
        while True:
            params = [("pattern", used), ("format", "xml"), ("pageLength", str(self.valves.MAX_RESULTS))]
            for book_id, _, _ in scoped[:10]:
                params.append(("books.name", book_id))
            try:
                root = ET.fromstring(self._get("/search?" + urllib.parse.urlencode(params)))
            except Exception as e:
                await self._status(__event_emitter__, "Library search failed", True)
                return f"Library search failed: {e}"
            items = list(root.iter("item"))
            if items or len(words) <= 2:
                break
            words = words[:-1]
            used = " ".join(words)
        lines = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            book = (item.findtext("book/title") or "").strip()
            d = item.find("description")
            snippet = " ".join("".join(d.itertext()).split()) if d is not None else ""
            lines.append(f"- {title}  [{book}]\n  link: {link}\n  {snippet[:300]}")
        await self._status(__event_emitter__, f"Found {len(lines)} results for “{query}”", True)
        if not lines:
            hint = " (try different keywords" + (", or no collection filter" if collection else "") + ")"
            return f"No results for '{query}'{hint}."
        scope = f" in {', '.join(t for _, t, _ in scoped[:3])}" if scoped else ""
        widened = f" (nothing matched every word, so these match '{used}')" if used != query else ""
        return f"Search results for '{query}'{scope}{widened}. Call read_article with a link to read one in full:\n\n" + "\n".join(lines)

    async def read_article(
        self,
        link: str,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> str:
        """
        Read the full text of one Reference Library article, guide or Q&A thread.
        Use a link returned by search_library (it starts with /content/).
        Long articles are shortened. Cite the article title when you use it.
        :param link: The article link from search_library, e.g. /content/ifixit_en_all_2025-12/Guide/...
        """
        path = link.strip()
        if path.startswith("http"):
            path = "/" + path.split("/", 3)[3]
        if not path.startswith("/content/"):
            return "That isn't a library link. Use a link from search_library (it starts with /content/)."
        await self._status(__event_emitter__, "Reading the article…")
        try:
            raw = self._get(urllib.parse.quote(path, safe="/%+?=&:"))
        except Exception as e:
            await self._status(__event_emitter__, "Could not open the article", True)
            return f"Could not open {path}: {e}"
        page = raw.decode("utf-8", "replace")
        m = re.search(r"<title>(.*?)</title>", page, re.S)
        title = html.unescape(m.group(1).strip()) if m else path.rsplit("/", 1)[-1]
        ex = _TextExtractor()
        ex.feed(page)
        text = ex.text()
        cut = len(text) > self.valves.MAX_ARTICLE_CHARS
        text = text[: self.valves.MAX_ARTICLE_CHARS] + ("\n\n[…article shortened…]" if cut else "")
        public = self.valves.PUBLIC_URL.rstrip("/") + path
        if __event_emitter__:
            await __event_emitter__({
                "type": "citation",
                "data": {"document": [text[:3000]], "metadata": [{"source": public, "name": title}], "source": {"name": title, "url": public}},
            })
        await self._status(__event_emitter__, f"Read: {title}", True)
        return f"# {title}\nSource: {public}\n\n{text}"
