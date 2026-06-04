from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st
import tweepy


def _get_secret(name: str) -> Optional[str]:
    """Fetch a secret from Streamlit, falling back to environment variables."""
    try:
        value = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - allow Streamlit-less contexts
        value = None
    if value:
        return str(value)
    return os.getenv(name)


def search_username(username: str) -> Dict[str, Any]:
    """Search for a username across platforms using Sherlock."""
    try:
        if not username:
            return {"success": False, "data": {}, "error": "Username is required"}
        base_args = [username, "--timeout", "10", "--print-found", "--no-color"]
        command_options = []
        sherlock_path = shutil.which("sherlock")
        if sherlock_path:
            command_options.append([sherlock_path, *base_args])
        command_options.append([sys.executable, "-m", "sherlock", *base_args])
        command_options.append([sys.executable, "-m", "sherlock.sherlock", *base_args])

        result = None
        output = ""
        error_text = ""
        for command in command_options:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            output = result.stdout or ""
            error_text = result.stderr or ""
            if output:
                break

        if not output and result and result.returncode != 0:
            return {
                "success": False,
                "data": {},
                "error": error_text.strip() or "Sherlock execution failed",
            }
        found = []
        pattern = re.compile(r"\[\+\]\s+(?P<platform>[^:]+):\s+(?P<url>\S+)")
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                found.append({"platform": match.group("platform").strip(), "url": match.group("url").strip()})

        return {
            "success": True,
            "data": {"username": username, "found_on": found, "total_found": len(found)},
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - return structured error
        return {"success": False, "data": {}, "error": str(exc)}


def search_twitter_keyword(keyword: str, max_results: int = 50) -> Dict[str, Any]:
    """Search recent tweets for a keyword using Twitter API v2."""
    try:
        bearer_token = _get_secret("TWITTER_BEARER_TOKEN")
        if not bearer_token:
            return {"success": False, "data": {}, "error": "Missing TWITTER_BEARER_TOKEN"}

        client = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)
        response = client.search_recent_tweets(
            query=keyword,
            max_results=max_results,
            tweet_fields=["created_at", "author_id", "public_metrics"],
        )
        tweets = []
        if response and response.data:
            for tweet in response.data:
                metrics = tweet.public_metrics or {}
                tweets.append(
                    {
                        "text": tweet.text,
                        "created_at": tweet.created_at.isoformat() if isinstance(tweet.created_at, datetime) else None,
                        "retweet_count": metrics.get("retweet_count", 0),
                        "like_count": metrics.get("like_count", 0),
                    }
                )

        return {
            "success": True,
            "data": {"keyword": keyword, "tweets": tweets, "total": len(tweets)},
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - return structured error
        return {"success": False, "data": {}, "error": str(exc)}


def get_twitter_trends(woeid: int = 1) -> Dict[str, Any]:
    """Fetch Twitter trends for a given WOEID using Twitter API v1.1."""
    try:
        api_key = _get_secret("TW_API_KEY")
        api_secret = _get_secret("TW_API_SECRET")
        access_token = _get_secret("TW_ACCESS_TOKEN")
        access_secret = _get_secret("TW_ACCESS_SECRET")
        if not all([api_key, api_secret, access_token, access_secret]):
            return {"success": False, "data": {}, "error": "Missing Twitter OAuth credentials"}

        auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
        api = tweepy.API(auth, wait_on_rate_limit=True)
        trends_result = api.get_place_trends(woeid)
        trends = []
        if trends_result:
            trend_list = trends_result[0].get("trends", [])
            sorted_trends = sorted(trend_list, key=lambda item: item.get("tweet_volume") or 0, reverse=True)
            for trend in sorted_trends[:20]:
                trends.append(
                    {
                        "name": trend.get("name"),
                        "volume": trend.get("tweet_volume") or 0,
                        "url": trend.get("url"),
                    }
                )

        return {"success": True, "data": {"trends": trends}, "error": None}
    except Exception as exc:  # noqa: BLE001 - return structured error
        return {"success": False, "data": {}, "error": str(exc)}
