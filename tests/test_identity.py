from src.parsing.identity import canonicalize_url, content_hash, deterministic_record_id


def test_canonical_url_drops_tracking_keeps_identity_parameters_and_is_stable() -> None:
    canonical = canonicalize_url(
        "http://EXAMPLE.com:80/paper/?id=42&utm_source=newsletter&b=2&a=1#heading"
    )

    assert canonical == "https://example.com/paper?a=1&b=2&id=42"
    assert deterministic_record_id("source-a", canonical) == deterministic_record_id(
        "source-a", canonical
    )
    assert deterministic_record_id("source-a", canonical) != deterministic_record_id(
        "source-b", canonical
    )


def test_content_hash_is_sha256_of_exact_raw_bytes() -> None:
    assert content_hash(b"source evidence") == "9c7c9338dc3e5d00303f4942fedceac6acba1d8ecf93149932d395407b5effdf"
