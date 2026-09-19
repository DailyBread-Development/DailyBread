from pathlib import Path  # noqa: I001


BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

DEVELOPMENT_GUILD_ID = "1512990445989396480"

STAFF_DOCUMENT_ROLES = {
    "1512991825764286544": "Staff Guide",
    "1512992978212356299": "Community Administration & Safety Staff Guide",
    "1512991672580182169": "Developer Staff Guide",
}

STAFF_DOCUMENTS = [
    {
        "slug": "staff-guide",
        "title": "Staff Guide",
        "role_id": "1512991825764286544",
        "directory": "staff_guides",
        "asset_base": "Staff Guide",
        "page_count": 3,
    },
    {
        "slug": "community-administration-safety-staff-guide",
        "title": "Community Administration & Safety Staff Guide",
        "role_id": "1512992978212356299",
        "directory": "mtm_guides",
        "asset_base": "MTM Guide",
        "page_count": 3,
    },
    {
        "slug": "developer-staff-guide",
        "title": "Developer Staff Guide",
        "role_id": "1512991672580182169",
        "directory": "dev_guides",
        "asset_base": "DEV Guide",
        "page_count": 3,
    },
]
