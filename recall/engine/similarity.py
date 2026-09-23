import hashlib
import math
from typing import Protocol


class SimilarityProvider(Protocol):
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Returns a similarity score between 0.0 and 1.0"""
        ...


class EmbeddingCache(Protocol):
    def get_string_embedding(self, text_hash: str) -> list[float] | None: ...
    def save_string_embedding(self, text_hash: str, embedding: list[float]) -> None: ...


class LexicalSimilarityProvider:
    def calculate_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, cache: EmbeddingCache | None = None, model: str = "text-embedding-3-small"):
        import openai

        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.cache = cache

    def _get_embedding(self, text: str) -> list[float]:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if self.cache:
            cached = self.cache.get_string_embedding(text_hash)
            if cached is not None:
                return cached

        response = self.client.embeddings.create(input=[text], model=self.model)
        vec = response.data[0].embedding

        if self.cache:
            self.cache.save_string_embedding(text_hash, vec)

        return vec

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return max(0.0, min(1.0, dot_product / (norm_a * norm_b)))

    def calculate_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0

        v1 = self._get_embedding(text1)
        v2 = self._get_embedding(text2)
        return self._cosine_similarity(v1, v2)
