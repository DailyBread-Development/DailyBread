from pathlib import Path  # noqa: I001


BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

DEVELOPMENT_GUILD_ID = "1512990445989396480"

STAFF_DOCUMENT_ROLES = {
    "1512991825764286544": "Staff Guide",
    "1512992978212356299": "Community Management & Safety Staff Guide",
    "1512991672580182169": "developer staff guide",
}

STAFF_DOCUMENTS = [
    {
        "slug": "staff-guide",
        "title": "Staff Guide",
        "role_id": "1512991825764286544",
        "asset_name": "staff-guide.svg",
    },
    {
        "slug": "community-management-safety-staff-guide",
        "title": "Community Management & Safety Staff Guide",
        "role_id": "1512992978212356299",
        "asset_name": "community-management-safety-staff-guide.svg",
    },
    {
        "slug": "developer-staff-guide",
        "title": "developer staff guide",
        "role_id": "1512991672580182169",
        "asset_name": "developer-staff-guide.svg",
    },
]
