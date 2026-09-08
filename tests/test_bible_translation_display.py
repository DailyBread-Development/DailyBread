import backend.services.bible_service as bible_service


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_parse_reference_query_returns_display_translation_label(monkeypatch):
    monkeypatch.setenv("nlt_bible_id", "78a9f6124f344018-01")
    monkeypatch.setenv("niv_bible_id", "4567890123456789-01")

    parsed = bible_service._parse_reference_query("NIV John 3:16")

    assert parsed["reference"] == "John 3:16"
    assert parsed["translations"] == ["4567890123456789-01"]
    assert parsed["translation_labels"] == ["NIV"]


def test_parse_reference_query_supports_explicit_translation_ids():
    parsed = bible_service._parse_reference_query("NIV:78a9f6124f344018-01 John 3:16")

    assert parsed["reference"] == "John 3:16"
    assert parsed["translations"] == ["78a9f6124f344018-01"]
    assert parsed["translation_labels"] == ["NIV"]


def test_api_bible_book_metadata_resolves_numbered_books(monkeypatch):
    monkeypatch.setenv("bible_api_key", "test-key")
    monkeypatch.setenv("bible_id", "test-bible")
    bible_service._BOOKS_CACHE.clear()
    monkeypatch.setattr(
        bible_service.requests,
        "get",
        lambda url, **kwargs: _Response({"data": [
            {"id": "1CO", "name": "I Corinthians", "nameLong": "The First Epistle of Paul the Apostle to the CORINTHIANS", "abbreviation": "1 Cor."},
            {"id": "1TH", "name": "1 Thes.", "nameLong": "1 Thessalonians", "abbreviation": "1 Thes."},
            {"id": "1JN", "name": "1 John", "nameLong": "1 John", "abbreviation": "1 Jn"},
        ]}),
    )

    assert bible_service._find_passage_id("1 Corinthians 16:14", "test-bible") == "1CO.16.14"
    assert bible_service._find_passage_id("1 Thessalonians 5:16", "test-bible") == "1TH.5.16"
    assert bible_service._find_passage_id("1 John 4:8", "test-bible") == "1JN.4.8"


def test_parse_reference_query_preserves_numbered_book_names(monkeypatch):
    monkeypatch.setenv("niv_bible_id", "niv-id")
    for book in ("1 Corinthians", "2 Corinthians", "1 Thessalonians", "2 Timothy", "1 Peter", "1 John"):
        parsed = bible_service._parse_reference_query(f"NIV {book} 3:16")
        assert parsed["reference"] == f"{book} 3:16"
        assert parsed["translations"] == ["niv-id"]
