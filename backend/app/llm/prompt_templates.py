from __future__ import annotations


def build_keyword_expansion_prompt(topic_name: str, seed_keywords: list[str]) -> str:
    return (
        "Expand search terms for the topic.\n"
        f"Topic: {topic_name}\n"
        f"Seed keywords: {', '.join(seed_keywords)}"
    )


def build_article_extraction_prompt(title: str, content: str) -> str:
    return (
        "Extract a short summary and stable keywords from the article.\n"
        f"Title: {title}\n"
        f"Content: {content}"
    )


def build_candidate_scoring_prompt(
    topic_name: str,
    candidate_title: str,
    candidate_summary: str,
) -> str:
    return (
        "Score how relevant the candidate is to the topic.\n"
        f"Topic: {topic_name}\n"
        f"Candidate title: {candidate_title}\n"
        f"Candidate summary: {candidate_summary}"
    )
