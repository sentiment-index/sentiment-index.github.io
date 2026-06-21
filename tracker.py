from enum import Enum
import hashlib
import itertools
import os
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import List, Tuple, Callable
from zoneinfo import ZoneInfo
from dateutil import parser

import praw
import requests

from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer, pipeline


# import my_secrets

SENTIMENT_BASE_DIR = "./sentiment-files"
DAYS = 365

model_id = "yangheng/deberta-v3-base-absa-v1.1"

tokenizer = AutoTokenizer.from_pretrained(
    model_id,
    use_fast=False
)
model = ORTModelForSequenceClassification.from_pretrained(
    model_id,
    export=True,
)

sentiment_pipeline = pipeline(
    "sentiment-analysis",
    model=model,
    tokenizer=tokenizer,
)

reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'), # or my_secrets.reddit_client_id,
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'), # or my_secrets.reddit_client_secret,
    user_agent="crawler"
)

class Source(Enum):
    REDDIT = "reddit"
    BLUESKY = "bluesky"

@dataclass
class WeightedPoint:
    value: float
    weight: int

    def append(self, new_value: float):
        self.value = (new_value + self.value * self.weight) / (self.weight + 1)
        self.weight = self.weight + 1

    def to_dict(self):
        return {
            "weight": self.weight,
            "value": self.value,
        }

    @staticmethod
    def from_dict(data: dict):
        return WeightedPoint(data.get("value", 0), data.get("weight", 0))

@dataclass
class RawData:
    scores: dict[str, WeightedPoint] = field(default_factory=dict)
    post_texts: list[int] = field(default_factory=list)

    def to_dict(self):
        return {
            "score": {key: value.to_dict() for key, value in self.scores.items()},
            "post_texts": self.post_texts
        }

    @staticmethod
    def from_dict(data: dict):
        return RawData(
            scores={key: WeightedPoint.from_dict(value) for key, value in data.get("score", {}).items()},
            post_texts=[x for x in data.get("post_texts", []) if isinstance(x, int)]
        )

def ensure_term_dir(term: str):
    term_dir = os.path.join(SENTIMENT_BASE_DIR, term)
    os.makedirs(term_dir, exist_ok=True)
    return term_dir

def search_bluesky(keyword: str, limit: int) -> List[Tuple[str, float]]:
    response = requests.get(
        "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
        {
            "q": keyword,
            "limit": limit,
            "since": (date.today() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        }
    )
    posts = response.json()["posts"]
    post_data = [(post["record"]["text"], parser.isoparse(post["record"]["createdAt"]).timestamp()) for post in posts]
    return post_data


def search_reddit(keyword: str, limit: int) -> List[Tuple[str, float]]:
    posts = list(reddit.subreddit("all").search(keyword, limit=limit // 2, sort="hot"))
    comments = []
    if len(posts) == 0:
        print(f"{keyword} returned 0 results...")
        posts = list(reddit.subreddit("all").search(keyword, limit=limit // 2))
        if len(posts) == 0:
            return []

    post = posts[0]
    post.comment_sort = "top"
    post.comments.replace_more(limit=0)
    if post.comments:
        comments = post.comments[0:min(len(post.comments), limit // 2)]

    combined_texts = [(post.title+"\n"+post.selftext, post.created_utc) for post in posts] + [(comment.body, comment.created_utc) for comment in comments]
    return combined_texts

searchers: dict[Source, Callable[[str, int], list[tuple[str, float]]]] = {
    Source.BLUESKY: search_bluesky,
    Source.REDDIT: search_reddit,
}


def stable_hash(text: str, timestamp: float) -> int:
    return int(hashlib.sha256((text+str(timestamp)).encode("utf-8")).hexdigest(), 16)

def analyze_post_sentiment(text: str, aspect: str) -> float:
    result = sentiment_pipeline(text[:512], text_pair=aspect)[0]
    return {"Negative": -1, "Neutral": 0, "Positive": 1}[result['label']] * result['score']

def serialize_raw_data(source: Source, term: str, data: RawData):
    term_dir = ensure_term_dir(term)
    with open(os.path.join(term_dir, source.value+"-scores-raw.json"), "w") as f:
        data.post_texts = data.post_texts # [-500:] # limit cache size
        json.dump(data.to_dict(), f, indent=2)

def load_raw_data(source: Source, term: str) -> RawData:
    term_dir = ensure_term_dir(term)
    path = os.path.join(term_dir, source.value+"-scores-raw.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return RawData.from_dict(json.load(f))
    return RawData()

def serialize_avg_data(term: str, avg_data: dict[Source, dict[str, float]]):
    term_dir = ensure_term_dir(term)
    cleaned_avg_data = {source.value: value for source, value in avg_data.items()}
    with open(os.path.join(term_dir, "avg-scores.json"), "w") as f:
        json.dump(cleaned_avg_data, f, indent=2)

def load_avg_sentiment_scores(term) -> dict[Source, dict[str, float]]:
    avg_path = os.path.join(SENTIMENT_BASE_DIR, term, "avg-scores.json")
    if not os.path.exists(avg_path):
        return {}
    with open(avg_path, "r") as f:
        str_source_json = json.load(f)
        return {Source(key): value for key, value in str_source_json.items()}

def compute_smoothed_avg(raw_data: dict[str, WeightedPoint]) -> dict[str, float]:
    today = datetime.now(ZoneInfo("UTC")).date()
    date_range = [today - timedelta(days=i) for i in range(DAYS)]
    smoothed = {}

    MIN_POSTS_FOR_AVG = 10
    MIN_INITIAL_DAYS = 4
    MAX_LOOKBACK_DAYS = 30

    for date in date_range:
        weighted_sum = 0.0
        total_weight = 0.0

        for offset in range(-MIN_INITIAL_DAYS, 1):
            nearby_date = date + timedelta(days=offset)
            key = str(nearby_date)

            if key in raw_data:
                point = raw_data[key]
                weighted_sum += point.value * point.weight
                total_weight += point.weight

        if total_weight < MIN_POSTS_FOR_AVG:
            for offset in range(-MIN_INITIAL_DAYS - 1, -MAX_LOOKBACK_DAYS - 1, -1):
                nearby_date = date + timedelta(days=offset)
                key = str(nearby_date)

                if key in raw_data:
                    point = raw_data[key]
                    weighted_sum += point.value * point.weight
                    total_weight += point.weight

                if total_weight >= MIN_POSTS_FOR_AVG:
                    break

        smoothed[str(date)] = (
            weighted_sum / total_weight
            if total_weight >= MIN_POSTS_FOR_AVG
            else 0.0
        )

    return smoothed

def update_term(term: str, searchers: dict[Source, Callable[[str, int], list[tuple[str, float]]]]) -> dict[Source, RawData]:
    source_posts = {source: searcher(term, 100) for source, searcher in searchers.items()}
    raw_data = {source: load_raw_data(source, term) for source in searchers}

    for source, posts in source_posts.items():
        for post in posts:
            created_date = datetime.fromtimestamp(post[1], tz=ZoneInfo("UTC")).date()
            date_key = str(created_date)
            text = post[0]
            text_hash = stable_hash(text, post[1])

            if text_hash not in raw_data[source].post_texts:
                sentiment_score = analyze_post_sentiment(text, term)
                raw_data[source].post_texts.append(text_hash)
                if date_key not in raw_data[source].scores:
                    raw_data[source].scores[date_key] = WeightedPoint(0,0)
                raw_data[source].scores[date_key].append(sentiment_score)
            else:
                # Bump it on the cache queue so it doesn't get removed
                raw_data[source].post_texts.remove(text_hash)
                raw_data[source].post_texts.append(text_hash)

    for source, raw_datum in raw_data.items():
        serialize_raw_data(source, term, raw_datum)

    smoothed_avgs = {source: compute_smoothed_avg(raw_datum.scores) for source, raw_datum in raw_data.items()}
    serialize_avg_data(term, smoothed_avgs)

    return raw_data

def update_all_terms():
    if not os.path.exists(SENTIMENT_BASE_DIR):
        return
    for term in get_term_list():
        update_term(term, searchers)

def add_term(term: str, populate: bool = True):
    ensure_term_dir(term)
    if populate:
        update_term(term, searchers)

def get_term_list() -> List[str]:
    if not os.path.exists(SENTIMENT_BASE_DIR):
        return []
    return [term for term in os.listdir(SENTIMENT_BASE_DIR) if not term.startswith(".")]

def get_newsworthy_terms(term_list: List[str]) -> List[str]:
    def replace_symbols_with_space(text):
        return re.sub(r'[^a-zA-Z0-9]', ' ', text)

    post_string = " ----\n ".join([
        " " + replace_symbols_with_space(post.title.lower()) + " \n " + (replace_symbols_with_space(post.selftext.lower()) or "") + " "
        for post in itertools.chain(reddit.subreddit("worldnews").hot(limit=700), reddit.subreddit("popculturechat").hot(limit=300), reddit.subreddit("science").hot(limit=100))
    ])

    sorted_term_list = sorted(term_list, key=lambda term: post_string.count(" " + term.lower() + " "), reverse=True)
    return sorted_term_list[:6]


# FOR TESTING ONLY
# def recompute_all_smoothed_scores():
#     for term in get_term_list():
#         raw_data = load_raw_data(term)
#         smoothed_avg = compute_smoothed_avg(raw_data.scores)
#         serialize_avg_data(term, smoothed_avg)

if __name__ == "__main__":
    pass
