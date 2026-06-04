from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import plotly.express as px
import streamlit as st

from modules.social_osint import get_twitter_trends, search_twitter_keyword, search_username


@st.cache_data
def _load_css(path: str) -> str:
    """Load CSS from disk for theming."""
    with open(path, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


@st.cache_data
def _cached_search_username(username: str) -> Dict[str, Any]:
    """Cached wrapper around Sherlock username search."""
    return search_username(username)


@st.cache_data
def _cached_search_twitter_keyword(keyword: str, max_results: int) -> Dict[str, Any]:
    """Cached wrapper around Twitter keyword search."""
    return search_twitter_keyword(keyword, max_results)


@st.cache_data
def _cached_get_trends(woeid: int) -> Dict[str, Any]:
    """Cached wrapper around Twitter trends."""
    return get_twitter_trends(woeid)


def _init_state() -> None:
    """Initialize session state keys for social intelligence."""
    if "case_log" not in st.session_state:
        st.session_state["case_log"] = []
    if "social_username" not in st.session_state:
        st.session_state["social_username"] = None
    if "social_keyword" not in st.session_state:
        st.session_state["social_keyword"] = None
    if "social_trends" not in st.session_state:
        st.session_state["social_trends"] = None
    if "social_last_result" not in st.session_state:
        st.session_state["social_last_result"] = None


css = _load_css("assets/style.css")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

_init_state()

st.title("Social Media Intelligence Dashboard")

username_tab, keyword_tab, trends_tab = st.tabs(["Username Search", "Keyword Monitor", "Trend Map"])

with username_tab:
    username = st.text_input("Username")
    if st.button("Search Username") and username:
        result = _cached_search_username(username)
        st.subheader("Results")
        data = result.get("data", {})
        found = data.get("found_on", [])
        st.dataframe(found, width="stretch")
        st.metric("Total Platforms Found", data.get("total_found", 0))

        urls_text = "\n".join([item.get("url", "") for item in found])
        st.text_area("Copy report", value=urls_text, height=150)

        record = {
            "module": "Social Media Intel - Username Search",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result.get("data", {}),
        }
        if st.session_state.get("social_username") != record:
            st.session_state["case_log"].append(record)
            st.session_state["social_username"] = record
        st.session_state["social_last_result"] = result

with keyword_tab:
    keyword = st.text_input("Keyword", key="keyword_input")
    max_results = st.slider("Max results", 10, 100, 50)
    if st.button("Search Keyword") and keyword:
        result = _cached_search_twitter_keyword(keyword, max_results)
        data = result.get("data", {})
        tweets = data.get("tweets", [])
        tweet_rows = [
            {
                "text": tweet.get("text"),
                "created_at": tweet.get("created_at"),
                "retweets": tweet.get("retweet_count", 0),
                "likes": tweet.get("like_count", 0),
            }
            for tweet in tweets
        ]
        st.dataframe(tweet_rows, width="stretch", height=320)

        if tweet_rows:
            for row in tweet_rows:
                row["engagement"] = (row.get("retweets") or 0) + (row.get("likes") or 0)
            chart = px.bar(tweet_rows, x="created_at", y="engagement", title="Engagement Over Time")
            st.plotly_chart(chart, width="stretch")

        record = {
            "module": "Social Media Intel - Keyword Monitor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result.get("data", {}),
        }
        if st.session_state.get("social_keyword") != record:
            st.session_state["case_log"].append(record)
            st.session_state["social_keyword"] = record
        st.session_state["social_last_result"] = result

with trends_tab:
    woeid_options = {
        "Worldwide": 1,
        "USA": 23424977,
        "India": 23424848,
        "UK": 23424975,
    }
    woeid_label = st.selectbox("Select region", options=list(woeid_options.keys()))
    woeid = woeid_options[woeid_label]
    if st.button("Fetch Trends"):
        result = _cached_get_trends(int(woeid))
        trends = result.get("data", {}).get("trends", [])
        sorted_trends = sorted(trends, key=lambda item: item.get("volume", 0), reverse=True)
        st.dataframe(sorted_trends, width="stretch")

        if sorted_trends:
            top_trends = sorted_trends[:10]
            chart = px.bar(top_trends, x="volume", y="name", orientation="h", title="Top Trends")
            st.plotly_chart(chart, width="stretch")

        record = {
            "module": "Social Media Intel - Trend Map",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result.get("data", {}),
        }
        if st.session_state.get("social_trends") != record:
            st.session_state["case_log"].append(record)
            st.session_state["social_trends"] = record
        st.session_state["social_last_result"] = result

download_payload = json.dumps(st.session_state.get("social_last_result") or {}, indent=2)
st.download_button(
    "Download Current Result JSON",
    data=download_payload,
    file_name="social_media_result.json",
    mime="application/json",
    disabled=st.session_state.get("social_last_result") is None,
)
