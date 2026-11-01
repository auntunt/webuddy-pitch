"""Code locations an agent's answer names (file plus line), however it writes them: `a.ts:78`, `a.ts` 第 78 行, a table row."""
import re

PATH = re.compile(r"[\w./\\-]+\.(?:java|cs|xml|sql|jsp|aspx|cshtml|config|properties|yml|yaml|vb|js|ts|vue|kt|py)(?![\w])", re.IGNORECASE)
GLUED = re.compile(r"^[`*'\"]*(?::|#L)(\d+)")
NEAR = re.compile(r"(?:第|\bline\b|行|\bL)\s*(\d+)|\|\s*(\d+)\s*(?:[-–~]\s*\d+\s*)?行?\s*\|", re.IGNORECASE)
REACH = 40


class CodeRefs:
    """Drop-in for the old file:line regex: `findall` gives (file, line) pairs, `search` whether there is any."""

    def findall(self, text: str) -> list:
        out = []
        for line in (text or "").splitlines():
            hits = list(PATH.finditer(line))
            for k, m in enumerate(hits):
                after = line[m.end():hits[k + 1].start() if k + 1 < len(hits) else len(line)][:REACH]
                n = GLUED.match(after) or NEAR.search(after)
                if n:
                    out.append((m.group(0), n.group(1) or n.group(2)))
        return out

    def search(self, text: str) -> bool:
        return bool(self.findall(text))


FILE_LINE = CodeRefs()
