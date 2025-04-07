import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import List, Dict, Set
from zoneinfo import ZoneInfo

import praw
from praw.models import Submission
from transformers import pipeline

SENTIMENT_BASE_DIR = "./sentiment-files"
DAYS = 365

sentiment_pipeline = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

@dataclass
class RawData:
    scores: Dict[str, List[float]] = field(default_factory=dict)
    post_texts: Set[str] = field(default_factory=set)

def ensure_term_dir(term: str):
    term_dir = os.path.join(SENTIMENT_BASE_DIR, term)
    os.makedirs(term_dir, exist_ok=True)
    return term_dir

def search_reddit(keyword: str, limit: int = 100) -> List[Submission]:
    reddit = praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        user_agent="crawler"
    )
    return list(reddit.subreddit("all").search(keyword, limit=limit, sort="hot"))


# scores normalized in [-1, 1]
# text limited to 512 chars
def analyze_post_sentiment(text: str) -> float:
    result = sentiment_pipeline(text[:512])[0]
    stars = int(result['label'].split()[0])
    # print("\t", text[:100].replace("\n", " "), stars)
    return (stars - 3) / 2

def serialize_raw_data(term: str, data: RawData):
    term_dir = ensure_term_dir(term)
    with open(os.path.join(term_dir, "scores-raw.pkl"), "wb") as f:
        pickle.dump(data, f)

def load_raw_data(term: str) -> RawData:
    term_dir = ensure_term_dir(term)
    path = os.path.join(term_dir, "scores-raw.pkl")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return RawData()

def serialize_avg_data(term: str, avg_data: Dict[str, float]):
    term_dir = ensure_term_dir(term)
    with open(os.path.join(term_dir, "scores-avg.pkl"), "wb") as f:
        pickle.dump(avg_data, f)

def compute_smoothed_avg(raw_data: Dict[str, List[float]]) -> Dict[str, float]:
    today = datetime.now(ZoneInfo("UTC")).date()
    date_range = [today - timedelta(days=i) for i in range(DAYS)]
    smoothed = {}

    for date in date_range:
        weighted_sum = 0
        total_posts = 0
        for offset in range(-4, 1):
            nearby_date = date + timedelta(days=offset)
            key = str(nearby_date)
            if key in raw_data:
                posts = raw_data[key]
                weighted_sum += sum(posts)
                total_posts += len(posts)
        smoothed[str(date)] = weighted_sum / total_posts if total_posts > 0 else 0.0

    return smoothed

def update_term(term: str):
    posts = search_reddit(term, limit=100)
    raw_data = load_raw_data(term)


    for post in posts:
        created_date = datetime.fromtimestamp(post.created_utc).date()
        date_key = str(created_date)
        text = post.title + "\n" + (post.selftext or "")

        if text not in raw_data.post_texts:
            sentiment_score = analyze_post_sentiment(text)

            raw_data.post_texts.add(text)
            if date_key not in raw_data.scores:
                raw_data.scores[date_key] = []
            raw_data.scores[date_key].append(sentiment_score)

    serialize_raw_data(term, raw_data)

    # print(raw_data.scores)

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
    term_dir = ensure_term_dir(term)
    avg_path = os.path.join(term_dir, "scores-avg.pkl")
    if not os.path.exists(avg_path):
        raise ValueError()
    with open(avg_path, "rb") as f:
        avg_data = pickle.load(f)
    with open(os.path.join(term_dir, "scores-raw.pkl"), "rb") as f:
        raw_data = pickle.load(f)
    # print("TOTAL POSTS", sum(len(score_day) for score_day in raw_data.scores.values()))
    return avg_data.get(day, 0.0)



def load_avg_sentiment_scores(term):
    avg_path = os.path.join(SENTIMENT_BASE_DIR, term, "scores-avg.pkl")
    if not os.path.exists(avg_path):
        return {}
    with open(avg_path, "rb") as f:
        return pickle.load(f)

def get_term_list() -> List[str]:
    if not os.path.exists(SENTIMENT_BASE_DIR):
        return []
    return os.listdir(SENTIMENT_BASE_DIR)

if __name__ == "__main__":
    """start = time.time()
        with open("terms.txt", "r") as file:
        for line in file:
            term = line.split("\n")[0]
            print(term, time.time()-start)
            add_term(term)
    with open("terms.txt", "r") as file:
        for line in file:

            term = line.split("\n")[0]

            print(term+":", get_sentiment_for_day(term))"""
    for term in get_term_list():
        print(term+":", get_sentiment_for_day(term))
    # add_term("nintendo")
    # print(get_sentiment_for_day("nintendo"))


