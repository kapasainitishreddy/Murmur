"""Dependency-free text intelligence for Murmur.

Everything here is pure Python so the backend stays lightweight: auto-tagging,
extractive summarization, lexicon sentiment, and TF-IDF cosine similarity that
powers semantic search, related murmurs, and duplicate detection.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Optional

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in", "on",
    "at", "by", "for", "with", "about", "as", "into", "like", "through", "after",
    "over", "between", "out", "against", "during", "without", "before", "under",
    "around", "among", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "should", "could", "can",
    "may", "might", "must", "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our", "their", "this", "that",
    "these", "those", "am", "just", "up", "down", "off", "not", "no", "yes", "get",
    "got", "there", "here", "when", "where", "what", "who", "how", "why", "which",
    "some", "any", "all", "more", "most", "than", "too", "very", "also", "from",
}

POSITIVE_WORDS = {
    "good", "great", "love", "loved", "happy", "excited", "excellent", "amazing",
    "wonderful", "perfect", "nice", "glad", "calm", "peaceful", "success", "win",
    "won", "resolved", "fixed", "done", "progress", "grateful", "thanks", "enjoy",
    "enjoyed", "smooth", "easy", "better", "best", "hope", "clear", "confident",
}

NEGATIVE_WORDS = {
    "bad", "hate", "hated", "sad", "angry", "afraid", "scared", "anxious", "worried",
    "broken", "crash", "crashed", "bug", "error", "fail", "failed", "failure",
    "problem", "issue", "damage", "damaged", "pain", "sick", "tired", "frustrated",
    "annoying", "wrong", "stuck", "delay", "delayed", "missing", "lost", "leak",
    "hard", "difficult", "worse", "worst", "confused", "stress", "stressed", "hurt",
}

_TOKEN_RE = re.compile(r"[a-z][a-z'-]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 2]


def extract_tags(text: str, limit: int = 5) -> list[str]:
    """Most salient content words, ordered by frequency then first appearance."""
    tokens = content_tokens(text)
    if not tokens:
        return []
    counts = Counter(tokens)
    order = {token: index for index, token in enumerate(tokens)}
    ranked = sorted(counts, key=lambda token: (-counts[token], order[token]))
    return ranked[:limit]


def summarize(text: str, max_sentences: int = 2) -> str:
    """Extractive summary: score sentences by content-word frequency, keep order."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    if len(parts) <= max_sentences:
        return " ".join(parts).strip() or text.strip()
    freq = Counter(content_tokens(text))
    scored = []
    for index, sentence in enumerate(parts):
        words = content_tokens(sentence)
        score = sum(freq[word] for word in words) / (len(words) + 1)
        scored.append((score, index, sentence))
    top = sorted(scored, key=lambda item: -item[0])[:max_sentences]
    ordered = sorted(top, key=lambda item: item[1])
    return " ".join(sentence for _, _, sentence in ordered)


def sentiment(text: str) -> dict[str, Any]:
    tokens = tokenize(text)
    positive = sum(1 for token in tokens if token in POSITIVE_WORDS)
    negative = sum(1 for token in tokens if token in NEGATIVE_WORDS)
    total = positive + negative
    score = 0.0 if total == 0 else round((positive - negative) / total, 3)
    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"
    return {"label": label, "score": score, "positive": positive, "negative": negative}


# --- TF-IDF cosine similarity -------------------------------------------------

def _term_frequencies(tokens: list[str]) -> Counter:
    return Counter(tokens)


def build_index(documents: list[str]) -> dict[str, Any]:
    """Precompute idf weights over a corpus for repeated similarity queries."""
    doc_tokens = [content_tokens(doc) for doc in documents]
    doc_count = len(doc_tokens)
    document_frequency: Counter = Counter()
    for tokens in doc_tokens:
        for token in set(tokens):
            document_frequency[token] += 1
    idf = {
        token: math.log((1 + doc_count) / (1 + freq)) + 1.0
        for token, freq in document_frequency.items()
    }
    return {"idf": idf, "doc_tokens": doc_tokens, "doc_count": doc_count}


def _vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _term_frequencies(tokens)
    length = len(tokens) or 1
    return {token: (count / length) * idf.get(token, math.log(2.0)) for token, count in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[token] * b[token] for token in common)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_by_similarity(query: str, documents: list[str]) -> list[tuple[int, float]]:
    """Return (document index, score) pairs sorted by relevance to the query."""
    if not documents:
        return []
    index = build_index(documents + [query])
    idf = index["idf"]
    query_vec = _vector(content_tokens(query), idf)
    scored = []
    for position, tokens in enumerate(index["doc_tokens"][:-1]):
        scored.append((position, round(_cosine(query_vec, _vector(tokens, idf)), 4)))
    scored.sort(key=lambda item: -item[1])
    return scored


def similarity(a: str, b: str) -> float:
    """Standalone cosine similarity between two short texts."""
    index = build_index([a, b])
    idf = index["idf"]
    return round(_cosine(_vector(content_tokens(a), idf), _vector(content_tokens(b), idf)), 4)


def most_similar(target: str, candidates: Iterable[tuple[str, str]], limit: int = 3, threshold: float = 0.08) -> list[dict[str, Any]]:
    """Rank (id, text) candidates against a target. Used for related murmurs."""
    candidates = list(candidates)
    if not candidates:
        return []
    texts = [text for _, text in candidates]
    ranked = rank_by_similarity(target, texts)
    results = []
    for position, score in ranked:
        if score < threshold:
            continue
        results.append({"id": candidates[position][0], "score": score})
        if len(results) >= limit:
            break
    return results


def find_duplicate(text: str, existing: Iterable[tuple[str, str]], threshold: float = 0.55) -> Optional[dict[str, Any]]:
    """Return the closest existing murmur above the similarity threshold, if any."""
    best = most_similar(text, existing, limit=1, threshold=threshold)
    return best[0] if best else None


def enrich(text: str) -> dict[str, Any]:
    """Bundle the per-murmur derived fields computed at save time."""
    return {
        "tags": extract_tags(text),
        "summary": summarize(text),
        "sentiment": sentiment(text),
    }
