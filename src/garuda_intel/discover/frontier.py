import heapq
from typing import List, Tuple


class Frontier:
    """
    Priority queue for URLs, ordered by score (desc), then depth (asc).
    """
    def __init__(self):
        self.heap: List[Tuple[float, int, str, str]] = []

    def push(self, score: float, depth: int, url: str, text: str):
        heapq.heappush(self.heap, (-score, depth, url, text))

    def pop(self):
        if not self.heap:
            return None
        neg_score, depth, url, text = heapq.heappop(self.heap)
        return -neg_score, depth, url, text

    def __len__(self):
        return len(self.heap)
