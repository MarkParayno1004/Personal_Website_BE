from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_admin
from models import PortfolioConfig, User
from schemas import PortfolioConfigResponse, PortfolioConfigUpdate

router = APIRouter(prefix="/portfolio", tags=["Portfolio Configuration"])

DEFAULT_CV_SKILLS = {
    "Languages": ["TypeScript", "JavaScript", "Dart", "Python", "PHP", "HTML", "CSS"],
    "Frontend": ["React", "Svelte", "Flutter", "Material UI", "Tailwind CSS", "Bootstrap"],
    "Backend": ["Django", "Laravel", "GraphQL", "REST APIs"],
    "Data": ["PostgreSQL", "MongoDB", "Firebase"],
    "Cloud & DevOps": ["AWS", "Jenkins", "CircleCI", "CI/CD"],
    "Practices": ["Agile/Scrum", "code review", "AI-assisted development (Cursor, Gemini)"],
}

DEFAULT_CV_EXPERIENCE = [
    {
        "role": "Software Specialist",
        "company": "Shopping Center Management Corporation (SM Prime Holdings, Inc.)",
        "location": "MOA Complex, Pasay City",
        "type": "Full-time",
        "period": "Sep 2024 - Present",
        "bullets": [
            "Build and maintain mobile and web apps with Flutter, Svelte, React, Python, Django, and Laravel for a high-traffic retail e-commerce ecosystem.",
            "Architected and maintained a centralized image asset database in Laravel where internal projects download media assets, complete with file import/export capabilities and dynamic file type conversion features.",
            "Deliver features on Svelte microsites for the company e-commerce platform new capabilities, production fixes, and UX improvements.",
            "Improve financial app performance by refactoring legacy code and eliminating N+1 queries, reducing database load and API response times.",
            "Support internal CMS apps that power the mobile e-commerce platform, keeping content workflows reliable for operations.",
            "Manage Jenkins and CircleCI deployments so builds, tests, and releases stay consistent and repeatable.",
            "Use Cursor and Gemini to accelerate feature work, refactoring, and debugging while upholding code quality standards.",
            "Contribute in Agile ceremonies: sprint planning, backlog refinement, stand-ups, reviews, and retrospectives.",
        ],
    },
    {
        "role": "Software Engineer Intern",
        "company": "Shopping Center Management Corporation (SM Prime Holdings, Inc.)",
        "location": "MOA Complex, Pasay City",
        "type": "Internship",
        "period": "Dec 2023 - May 2024",
        "bullets": [
            "Contributed features and maintenance across mobile and web applications in an Agile engineering team.",
            "Refactored Flutter/Dart codebases for readability, stability, and smoother QA handoff, delivered APK builds for testing.",
            "Joined brainstorming, code reviews, and end-to-end testing with QA throughout the sprint cycle.",
        ],
    },
    {
        "role": "IT Support Intern",
        "company": "National University",
        "location": "Sampaloc, Manila",
        "type": "Internship",
        "period": "May 2024 - Jun 2024",
        "bullets": [
            "Resolved hardware and software issues for faculty and staff to minimize downtime during academic operations.",
            "Supported enrollment by creating and updating IDs; maintained computer labs for classes, meetings, and presentations.",
        ],
    },
]

DEFAULT_CV_EDUCATION = [
    {
        "degree": "B.S. Information Technology, Mobile & Web Application",
        "institution": "National University Philippines, Manila",
        "graduation_date": "Sep 2024",
    }
]

DEFAULT_THEME_CONFIG = {
    "primary_color": "#2563eb",
    "dark_mode_default": True,
    "show_github_repos": True,
    "show_linkedin_posts": True,
    "section_order": [
        "hero",
        "about",
        "skills",
        "experience",
        "github",
        "linkedin",
        "education",
        "contact",
    ],
}


def _get_or_create_portfolio_config(db: Session) -> PortfolioConfig:
    config = db.query(PortfolioConfig).first()
    if not config:
        config = PortfolioConfig(
            full_name="Mark Philip V. Parayno",
            headline="Software Engineer | Mobile & Web Applications",
            location="San Juan City, Philippines",
            phone="+63 961 312 8973",
            email="paraynomarkphilip@gmail.com",
            linkedin_url="https://www.linkedin.com/in/mark-philip-parayno/",
            github_username="MarkParayno1004",
            about_summary=(
                "Software Engineer with production experience building and maintaining mobile and web applications "
                "for a large retail enterprise. Strong across Flutter, Svelte, React, Django, and Laravel. Focused on "
                "shipping reliable features, improving performance, and keeping delivery pipelines healthy in Agile teams."
            ),
            skills=DEFAULT_CV_SKILLS,
            experience=DEFAULT_CV_EXPERIENCE,
            education=DEFAULT_CV_EDUCATION,
            theme_config=DEFAULT_THEME_CONFIG,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get("/config", response_model=PortfolioConfigResponse)
def get_portfolio_config(db: Session = Depends(get_db)):
    """
    Public Endpoint: Retrieve current Portfolio Configuration & CV Details.
    Auto-initializes with Mark Philip V. Parayno's CV details if empty.
    """
    return _get_or_create_portfolio_config(db)


@router.put("/config", response_model=PortfolioConfigResponse)
def update_portfolio_config(
    update_data: PortfolioConfigUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin),
):
    """
    Admin Endpoint: Update and reconfigure portfolio profile, skills, experience,
    education, contact info, and theme settings.
    """
    config = _get_or_create_portfolio_config(db)

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if value is not None:
            setattr(config, field, value)

    db.commit()
    db.refresh(config)
    return config
