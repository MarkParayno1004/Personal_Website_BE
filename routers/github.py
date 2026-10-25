import logging
import os
from fastapi import APIRouter, HTTPException, Query, status
import httpx
from redis_cache import get_cache, set_cache
from schemas import GitHubRepo

router = APIRouter(prefix="/github", tags=["GitHub"])
logger = logging.getLogger("github")

GITHUB_CACHE_TTL_SECONDS = 600


@router.get("/repos", response_model=list[GitHubRepo])
async def get_repositories(
    username: str | None = Query(
        default=None,
        # GitHub's own username rules; also stops path tricks like "../../user/repos" reaching the API
        pattern=r"^[A-Za-z0-9-]{1,39}$",
        description="GitHub username to fetch public repositories for",
    ),
    limit: int = Query(default=10, ge=1, le=100, description="Max repositories to return"),
):
    """
    Fetch public repositories for the specified user from GitHub's REST API.
    Designed to power the projects/portfolio section in the frontend.
    """
    target_username = username or os.getenv("GITHUB_USERNAME")
    if not target_username:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub username is not configured",
        )

    cache_key = f"cache:github:{target_username.lower()}:{limit}"
    cached = get_cache(cache_key)
    if cached:
        return [GitHubRepo(**repo) for repo in cached]

    github_token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Personal-Portfolio-App",
    }
    if github_token:
        auth_prefix = "Bearer" if github_token.startswith("github_pat_") else "token"
        headers["Authorization"] = f"{auth_prefix} {github_token}"

    url = f"https://api.github.com/users/{target_username}/repos"
    params = {"sort": "updated", "per_page": limit}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
    except Exception as e:
        logger.warning("GitHub request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Server can't access GitHub right now",
        )

    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GitHub user not found")
    if response.status_code != 200:
        logger.warning("GitHub API error %s: %s", response.status_code, response.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub API error",
        )

    repos = [
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
        for repo in response.json()
    ]
    set_cache(cache_key, [repo.model_dump(mode="json") for repo in repos], ttl=GITHUB_CACHE_TTL_SECONDS)
    return repos
