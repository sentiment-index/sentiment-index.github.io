import hashlib
import os
import re
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from typing import List, Dict, Set, Tuple
from zoneinfo import ZoneInfo

import praw
from praw.models import Submission
from transformers import pipeline


SENTIMENT_BASE_DIR = "./sentiment-files"
DAYS = 365


sentiment_pipeline = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'), # or my_secrets.client_id,
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'), # or my_secrets.client_secret,
    user_agent="crawler"
)

@dataclass
class RawData:
    scores: Dict[str, List[float]] = field(default_factory=dict)
    post_texts: Set[int] = field(default_factory=set)

    def to_dict(self):
        return {
            "scores": self.scores,
            "post_texts": list(self.post_texts)
        }

    @staticmethod
    def from_dict(data: dict):
        return RawData(
            scores=data.get("scores", {}),
            post_texts=set([x for x in data.get("post_texts", []) if isinstance(x, int)])
        )

def ensure_term_dir(term: str):
    term_dir = os.path.join(SENTIMENT_BASE_DIR, term)
    os.makedirs(term_dir, exist_ok=True)
    return term_dir

def search_reddit(keyword: str, limit: int = 100) -> List[Tuple[str, float]]:
    posts = list(reddit.subreddit("all").search(keyword, limit=limit // 2, sort="hot"))
    comments = []

    for post in posts:
        post.comment_sort = "top"
        post.comments.replace_more(limit=0)
        if post.comments:
            top_comment = post.comments[0]
            comments.append(top_comment)

    combined_texts = [(post.title+"\n"+post.selftext, post.created_utc) for post in posts] + [(comment.body, comment.created_utc) for comment in comments]

    return combined_texts

def stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)

def analyze_post_sentiment(text: str) -> float:
    result = sentiment_pipeline(text[:512])[0]
    stars = int(result['label'].split()[0])
    return (stars - 3) / 2

def serialize_raw_data(term: str, data: RawData):
    term_dir = ensure_term_dir(term)
    with open(os.path.join(term_dir, "scores-raw.json"), "w") as f:
        json.dump(data.to_dict(), f, indent=2)

def load_raw_data(term: str) -> RawData:
    term_dir = ensure_term_dir(term)
    path = os.path.join(term_dir, "scores-raw.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return RawData.from_dict(json.load(f))
    return RawData()

def serialize_avg_data(term: str, avg_data: Dict[str, float]):
    term_dir = ensure_term_dir(term)
    with open(os.path.join(term_dir, "scores-avg.json"), "w") as f:
        json.dump(avg_data, f, indent=2)

def load_avg_sentiment_scores(term):
    avg_path = os.path.join(SENTIMENT_BASE_DIR, term, "scores-avg.json")
    if not os.path.exists(avg_path):
        return {}
    with open(avg_path, "r") as f:
        return json.load(f)

def compute_smoothed_avg(raw_data: Dict[str, List[float]]) -> Dict[str, float]:
    today = datetime.now(ZoneInfo("UTC")).date()
    date_range = [today - timedelta(days=i) for i in range(DAYS)]
    smoothed = {}

    MIN_POSTS_FOR_AVG = 10
    MIN_INITIAL_DAYS = 4
    MAX_LOOKBACK_DAYS = 30

    for date in date_range:
        weighted_sum = 0
        total_posts = 0
        for offset in range(-MIN_INITIAL_DAYS, 1):
            nearby_date = date + timedelta(days=offset)
            key = str(nearby_date)
            if key in raw_data:
                posts = raw_data[key]
                weighted_sum += sum(posts)
                total_posts += len(posts)
        if total_posts < MIN_POSTS_FOR_AVG:
            for offset in range(-MIN_INITIAL_DAYS - 1, -MAX_LOOKBACK_DAYS - 1, -1):
                nearby_date = date + timedelta(days=offset)
                key = str(nearby_date)
                if key in raw_data:
                    posts = raw_data[key]
                    weighted_sum += sum(posts)
                    total_posts += len(posts)
                if total_posts >= MIN_POSTS_FOR_AVG:
                    break

        smoothed[str(date)] = weighted_sum / total_posts if total_posts > MIN_POSTS_FOR_AVG else 0.0

    return smoothed

def update_term(term: str):
    posts = search_reddit(term, limit=100)
    raw_data = load_raw_data(term)

    for post in posts:
        created_date = datetime.fromtimestamp(post[1]).date()
        date_key = str(created_date)
        text = post[0]
        text_hash = stable_hash(text)

        if text_hash not in raw_data.post_texts:
            sentiment_score = analyze_post_sentiment(text)
            raw_data.post_texts.add(text_hash)
            if date_key not in raw_data.scores:
                raw_data.scores[date_key] = []
            raw_data.scores[date_key].append(sentiment_score)

    serialize_raw_data(term, raw_data)
    smoothed_avg = compute_smoothed_avg(raw_data.scores)
    serialize_avg_data(term, smoothed_avg)

def update_all_terms():
    if not os.path.exists(SENTIMENT_BASE_DIR):
        return
    for term in get_term_list():
        update_term(term)

def add_term(term: str, populate: bool = True):
    ensure_term_dir(term)
    if populate:
        update_term(term)

def get_sentiment_for_day(term: str, day: date = None) -> float:
    if day is None:
        day = str(datetime.now(ZoneInfo("UTC")).date())
    elif isinstance(day, date):
        day = str(day)

    term_dir = ensure_term_dir(term)
    avg_path = os.path.join(term_dir, "scores-avg.json")
    if not os.path.exists(avg_path):
        raise ValueError(f"No average sentiment data found for term '{term}'.")

    with open(avg_path, "r") as f:
        avg_data = json.load(f)
    return avg_data.get(day, 0.0)

def get_term_list() -> List[str]:
    if not os.path.exists(SENTIMENT_BASE_DIR):
        return []
    return [term for term in os.listdir(SENTIMENT_BASE_DIR) if not term.startswith(".")]

def get_newsworthy_terms(term_list: List[str]) -> List[str]:
    def replace_symbols_with_space(text):
        return re.sub(r'[^a-zA-Z0-9]', ' ', text)

    post_string = " ----\n ".join([
        " " + replace_symbols_with_space(post.title.lower()) + " \n " + (replace_symbols_with_space(post.selftext.lower()) or "") + " "
        for post in reddit.subreddit("all").hot(limit=1000)
    ])

    sorted_term_list = sorted(term_list, key=lambda term: post_string.count(" " + term.lower() + " "), reverse=True)
    return sorted_term_list[:6]


def recompute_all_smoothed_scores():
    for term in get_term_list():
        raw_data = load_raw_data(term)
        smoothed_avg = compute_smoothed_avg(raw_data.scores)
        serialize_avg_data(term, smoothed_avg)

if __name__ == "__main__":
    pass
