import json

from botocore.exceptions import ClientError

from arkminter import arkminter


def test_format_metadata_uses_supplied_nma_and_optional_fields():
    ark = arkminter.build_ark_identifier(naan="99999", shoulder="")
    metadata = json.loads(
        arkminter.format_metadata(
            nma="resolver.example.org",
            ark=ark,
            title="Example",
            creator="Library",
            date="2026-04-01",
        )
    )

    assert ark.startswith("ark:99999/")
    assert metadata["@id"] == f"https://resolver.example.org/{ark}"
    assert metadata["identifier"] == ark
    assert metadata["url"] == f"https://resolver.example.org/{ark}"
    assert metadata["name"] == "Example"
    assert metadata["creator"] == "Library"
    assert metadata["dateCreated"] == "2026-04-01"


def test_format_metadata_omits_optional_fields_when_empty():
    ark = arkminter.build_ark_identifier(naan="99999", shoulder="")
    metadata = json.loads(
        arkminter.format_metadata(
            nma="resolver.example.org",
            ark=ark,
        )
    )

    assert ark.startswith("ark:99999/")
    assert metadata["@id"] == f"https://resolver.example.org/{ark}"
    assert metadata["url"] == f"https://resolver.example.org/{ark}"
    assert "name" not in metadata
    assert "creator" not in metadata
    assert "dateCreated" not in metadata


def test_generate_betanumeric_string_defaults_to_5_characters():
    segment = arkminter.generate_betanumeric_string()
    assert len(segment) == 5


def test_generate_betanumeric_string_uses_supplied_blade_length():
    segment = arkminter.generate_betanumeric_string(blade_length=8)
    assert len(segment) == 7


def test_put_objects_writes_redirect_and_metadata_objects():
    calls = []

    class FakeS3:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    arkminter.put_objects(
        "resolver-bucket",
        ark="ark:99999/test1234",
        redirect_location="https://example.org/object",
        metadata={"identifier": "ark:99999/test1234"},
        s3_client=FakeS3(),
    )

    assert len(calls) == 2
    assert calls[0]["Bucket"] == "resolver-bucket"
    assert calls[0]["Key"] == "ark:99999/test1234/index.html"
    assert calls[0]["ContentType"] == "text/html; charset=utf-8"
    redirect_body = calls[0]["Body"].decode()
    assert 'id="r"' in redirect_body
    assert "window.location.replace(" in redirect_body
    assert 'href="https://example.org/object"' in redirect_body
    assert ">ark:99999/test1234<" in redirect_body
    assert calls[1]["Bucket"] == "resolver-bucket"
    assert calls[1]["Key"] == "ark:99999/test1234/info.jsonld"
    assert calls[1]["ContentType"] == "application/ld+json"
    body = calls[1]["Body"].decode()
    payload = json.loads(body)
    assert payload["identifier"] == "ark:99999/test1234"


def test_put_objects_uses_title_for_redirect_link_text():
    calls = []

    class FakeS3:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    arkminter.put_objects(
        "resolver-bucket",
        ark="ark:99999/test1234",
        redirect_location="https://example.org/object",
        metadata={"identifier": "ark:99999/test1234", "title": "Finding Aid"},
        s3_client=FakeS3(),
    )

    redirect_body = calls[0]["Body"].decode()
    assert ">Finding Aid<" in redirect_body


def test_mint_ark_runs_full_flow_and_returns_ark(monkeypatch):
    put_calls = []
    fake_client = object()
    reserve_calls = []

    def fake_reserve_ark(**kwargs):
        reserve_calls.append(kwargs)
        return "ark:99999/test1234"

    def fake_put_objects(bucket_name, ark, redirect_location, metadata, s3_client=None):
        put_calls.append(
            {
                "bucket_name": bucket_name,
                "ark": ark,
                "redirect_location": redirect_location,
                "metadata": metadata,
                "s3_client": s3_client,
            }
        )

    monkeypatch.setattr(arkminter, "reserve_ark", fake_reserve_ark)
    monkeypatch.setattr(arkminter, "put_objects", fake_put_objects)

    ark = arkminter.mint_ark(
        bucket_name="resolver-bucket",
        redirect_target="https://example.org/object",
        nma="resolver.example.org",
        naan="99999",
        title="Example",
        creator="Library",
        date="2026-04-01",
        shoulder="",
        blade_length=6,
        s3_client=fake_client,
    )

    assert ark == "ark:99999/test1234"
    assert reserve_calls[0]["bucket_name"] == "resolver-bucket"
    assert reserve_calls[0]["naan"] == "99999"
    assert reserve_calls[0]["s3_client"] is fake_client
    assert len(put_calls) == 1
    assert put_calls[0]["bucket_name"] == "resolver-bucket"
    assert put_calls[0]["redirect_location"] == "https://example.org/object"
    assert put_calls[0]["metadata"]["identifier"] == ark
    assert put_calls[0]["s3_client"] is fake_client


def test_mint_ark_builds_redirect_location_from_redirect_domain(monkeypatch):
    put_calls = []
    fake_client = object()

    def fake_reserve_ark(**kwargs):
        return "ark:99999/test1234"

    def fake_put_objects(bucket_name, ark, redirect_location, metadata, s3_client=None):
        put_calls.append(
            {
                "redirect_location": redirect_location,
            }
        )

    monkeypatch.setattr(arkminter, "reserve_ark", fake_reserve_ark)
    monkeypatch.setattr(arkminter, "put_objects", fake_put_objects)

    arkminter.mint_ark(
        bucket_name="resolver-bucket",
        redirect_domain="resolver.example.org",
        nma="resolver.example.org",
        naan="99999",
        s3_client=fake_client,
    )

    assert (
        put_calls[0]["redirect_location"]
        == "https://resolver.example.org/ark:99999/test1234"
    )


def test_reserve_ark_is_atomic():
    calls = []

    class FakeS3:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    def fake_build_ark_identifier(*args, **kwargs):
        return "ark:99999/test1234"

    original_builder = arkminter.build_ark_identifier
    arkminter.build_ark_identifier = fake_build_ark_identifier

    try:
        reserved = arkminter.reserve_ark(
            bucket_name="resolver-bucket",
            naan="99999",
            s3_client=FakeS3(),
        )
    finally:
        arkminter.build_ark_identifier = original_builder

    assert reserved == "ark:99999/test1234"
    assert calls[0]["Bucket"] == "resolver-bucket"
    assert calls[0]["Key"] == "ark:99999/test1234/index.html"
    assert calls[0]["ContentType"] == "text/html; charset=utf-8"
    assert calls[0]["IfNoneMatch"] == "*"
    assert calls[0]["Body"] == b""


def test_reserve_ark_retries_until_unique(monkeypatch):
    sequence = ["ark:99999/existingark", "ark:99999/newark"]

    def fake_build_ark_identifier(*args, **kwargs):
        return sequence.pop(0)

    class FakeS3:
        def put_object(self, **kwargs):
            if kwargs["Key"] == "ark:99999/existingark/index.html":
                raise ClientError(
                    {
                        "Error": {
                            "Code": "PreconditionFailed",
                            "Message": "Object already exists",
                        }
                    },
                    "PutObject",
                )
            return {}

    monkeypatch.setattr(arkminter, "build_ark_identifier", fake_build_ark_identifier)

    reserved = arkminter.reserve_ark(
        bucket_name="resolver-bucket",
        naan="99999",
        max_attempts=3,
        s3_client=FakeS3(),
    )

    assert reserved == "ark:99999/newark"
