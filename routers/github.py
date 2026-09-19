import os
from fastapi import APIRouter, HTTPException, Query, status
import httpx
from schemas import GitHubRepo

router = APIRouter(prefix="/github", tags=["GitHub"])


@router.get("/repos", response_model=list[GitHubRepo])
async def get_repositories(
    username: str | None = Query(
        default=None,
        description="GitHub username to fetch public repositories for",
    ),
    limit: int = Query(default=10, ge=1, le=100, description="Max repositories to return"),
):
    """
    Fetch public repositories for the specified user from GitHub's REST API.
    Designed to power the projects/portfolio section in the frontend.
    """
    target_username = username or os.getenv("GITHUB_USERNAME")
    github_token = os.getenv("GITHUB_TOKEN")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Personal-Portfolio-App",
    }
    if github_token:
        auth_prefix = "Bearer" if github_token.startswith("github_pat_") else "token"
        headers["Authorization"] = f"{auth_prefix} {github_token}"

    url = f"https://api.github.com/users/{target_username}/repos?sort=updated&per_page={limit}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                repos_data = response.json()
                return [
                    GitHubRepo(
                        id=repo["id"],
                        name=repo["name"],
                        full_name=repo["full_name"],
                        html_url=repo["html_url"],
                        description=repo.get("description"),
                        language=repo.get("language"),
                        stars=repo.get("stargazers_count", 0),
                        forks=repo.get("forks_count", 0),
                        updated_at=repo.get("updated_at"),
                    )
                    for repo in repos_data
                ]

            try:
                error_msg = response.json().get("message", response.text)
            except Exception:
                error_msg = response.text

            raise HTTPException(
                status_code=response.status_code if response.status_code >= 400 else status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub API Error: {error_msg}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Server can't access GitHub: {str(e)}",
        )