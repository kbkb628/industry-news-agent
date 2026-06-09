def enqueue_topic_run(topic_id: str) -> dict[str, str]:
    return {"topic_id": topic_id, "status": "scheduled"}
