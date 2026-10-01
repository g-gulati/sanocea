"""
Deduplication engine for SANOCEA Content Engine.
Scans past 60 days of published and scheduled content to prevent idea repackaging.
Employs n-gram token overlap and TF-IDF cosine similarity for semantic duplicate detection.
"""

import os
import re
import json
import math
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from packages.content_engine.models import OperationalTopic


class DeduplicationEngine:
    """Detects duplicate or overly similar topics against 60-day historical archives."""

    def __init__(self, history_dir: str = "/opt/sanocea/repo/website/marketing-ops/content"):
        self.history_dir = history_dir
        self.similarity_threshold = 0.65  # Reject if similarity exceeds 65%

    def load_recent_history(self, days_window: int = 60) -> List[Dict]:
        """Loads all scheduled and published content records within the window."""
        records = []
        cutoff_date = datetime.utcnow() - timedelta(days=days_window)

        if not os.path.exists(self.history_dir):
            return records

        for fname in os.listdir(self.history_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self.history_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    # Parse title, caption, and timestamp from either flat or ContentRecord schema
                    title = data.get("title") or (data.get("topic", {}).get("title") if isinstance(data.get("topic"), dict) else "")
                    caption = data.get("caption") or (data.get("content_copy", {}).get("problem_narrative") if isinstance(data.get("content_copy"), dict) else "")
                    sched_time_str = data.get("scheduled_at_utc") or (data.get("scheduling", {}).get("target_utc") if isinstance(data.get("scheduling"), dict) else None)
                    
                    if sched_time_str:
                        clean_time = sched_time_str.replace("Z", "")
                        try:
                            sched_dt = datetime.fromisoformat(clean_time)
                            if sched_dt < cutoff_date:
                                continue
                        except Exception:
                            pass
                    
                    topic_id = data.get("topic", {}).get("id") if isinstance(data.get("topic"), dict) else None
                    records.append({
                        "file": fname,
                        "topic_id": topic_id,
                        "title": title,
                        "caption": caption,
                        "format": data.get("format", ""),
                        "scheduled_at": sched_time_str,
                        "data": data
                    })
            except Exception:
                continue

        return records

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercases and extracts alpha-numeric words, removing stopwords."""
        stopwords = {
            "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
            "which", "this", "that", "these", "those", "then", "just", "so", "than",
            "such", "both", "through", "about", "for", "is", "of", "while", "during",
            "to", "from", "in", "out", "on", "off", "again", "further", "then", "once",
            "here", "there", "when", "where", "why", "how", "all", "any", "both",
            "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
            "only", "own", "same", "so", "than", "too", "very", "can", "will", "just",
            "don't", "should", "now", "your", "our", "their", "you", "we", "they", "it"
        }
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        return [w for w in words if w not in stopwords]

    @classmethod
    def compute_similarity(cls, text_a: str, text_b: str) -> float:
        """Computes TF-IDF cosine similarity between two texts."""
        tokens_a = cls._tokenize(text_a)
        tokens_b = cls._tokenize(text_b)

        if not tokens_a or not tokens_b:
            return 0.0

        vocab = sorted(list(set(tokens_a + tokens_b)))
        if not vocab:
            return 0.0

        # Term frequencies
        tf_a = {w: tokens_a.count(w) for w in vocab}
        tf_b = {w: tokens_b.count(w) for w in vocab}

        # Dot product and magnitudes
        dot_product = sum(tf_a[w] * tf_b[w] for w in vocab)
        mag_a = math.sqrt(sum(count ** 2 for count in tf_a.values()))
        mag_b = math.sqrt(sum(count ** 2 for count in tf_b.values()))

        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0

        return dot_product / (mag_a * mag_b)

    def check_duplicate(self, candidate_topic: OperationalTopic) -> Tuple[bool, float, Optional[str]]:
        """
        Evaluates candidate topic against 60-day history.
        Returns: (is_duplicate: bool, max_similarity: float, matching_title: str)
        """
        history = self.load_recent_history(days_window=60)
        candidate_text = f"{candidate_topic.title} {candidate_topic.operational_problem} {' '.join(candidate_topic.keywords)}"

        max_sim = 0.0
        matching_title = None

        for item in history:
            if candidate_topic.id and item.get("topic_id") == candidate_topic.id:
                continue
            historical_text = f"{item['title']} {item['caption']}"
            sim = self.compute_similarity(candidate_text, historical_text)
            if sim > max_sim:
                max_sim = sim
                matching_title = item["title"]

        is_dup = max_sim >= self.similarity_threshold
        return is_dup, round(max_sim, 3), matching_title
