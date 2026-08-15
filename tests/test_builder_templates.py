from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_guild_builder_uses_existing_switch_for_embed_and_container_modes():
    template = (ROOT / "frontend" / "templates" / "pages" / "guild-builder.html").read_text(encoding="utf-8")

    assert "Normal Embed" in template
    assert "Advanced Container" in template
    assert "container-components" in template


def test_dashboard_builder_page_no_longer_uses_duplicate_mode_switch():
    template = (ROOT / "frontend" / "templates" / "pages" / "builder.html").read_text(encoding="utf-8")

    assert "id=\"mode-normal\"" not in template
    assert "id=\"mode-advanced\"" not in template
