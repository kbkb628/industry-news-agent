from fastapi.testclient import TestClient


def test_health_endpoint_exists(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_html_pages_expose_showcase_navigation_and_resume_copy(
    client: TestClient,
) -> None:
    topics_response = client.get("/")
    resume_response = client.get("/resume-alignment")
    history_response = client.get("/history-search")

    assert topics_response.status_code == 200
    assert "Showcase Navigation" in topics_response.text
    assert "Resume Alignment" in topics_response.text
    assert "History Search" in topics_response.text
    assert "Recruiter-ready console" in topics_response.text
    assert "Agent workflow highlights" in topics_response.text

    assert resume_response.status_code == 200
    assert "Resume Alignment" in resume_response.text
    assert "Interview talking points" in resume_response.text
    assert "RAG grounding evidence" in resume_response.text

    assert history_response.status_code == 200
    assert "History Search" in history_response.text
    assert "candidate-history retrieval" in history_response.text
