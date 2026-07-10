import configparser
import html
import json
import logging
import logging.config
import random
import re

from pathlib import Path
from urllib.parse import unquote

from botocore.exceptions import ClientError

# IMPORTANT: BETANUMERICS must match the character list exactly in the order it
# is found in the resolver source code because calculate_check_digit() uses the
# index of each character as its numeric value.
BETANUMERICS = "0123456789bcdfghjkmnpqrstvwxz"


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def setup_logging(config_file="logging.conf"):
    config_path = Path(config_file)
    if config_path.exists():
        config = configparser.ConfigParser()
        try:
            config.read(config_file)
            logging.config.fileConfig(config_file)
        except Exception as e:
            print(f"ERROR READING {config_file}: {e}")
            fallback_logging()
    else:
        fallback_logging()


def fallback_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("LOGGING CONFIGURED USING basicConfig FALLBACK")


def calculate_check_digit(identifier: str) -> str:
    # XDIGIT includes '/' because ARK check zones are computed over "NAAN/name".
    XDIGIT = BETANUMERICS + "/"
    total = 0
    for i, ch in enumerate(identifier.lower()):
        idx = XDIGIT.find(ch)
        if idx == -1:
            raise ValueError(f"Invalid character {ch} for check digit calculation")
        total += (i + 1) * idx
    return XDIGIT[total % len(XDIGIT)]


def generate_betanumeric_string(blade_length: int = 6) -> str:
    segment_length = blade_length - 1
    return "".join(random.choice(BETANUMERICS) for _ in range(segment_length))


def format_metadata(
    nma: str,
    ark: str,
    title: str = "",
    creator: str = "",
    date: str = "",
) -> str:
    metadata = {
        "@context": "https://schema.org",
        "@id": "https://" + nma + "/" + ark,
        "@type": "ArchiveComponent",
        "identifier": ark,
    }
    if title:
        metadata["name"] = title
    if creator:
        metadata["creator"] = creator
    if date:
        metadata["dateCreated"] = date
    metadata["url"] = metadata["@id"]
    return json.dumps(metadata, indent=2)


def get_existing_our_ark(archival_object: dict, naan: str) -> str | None:
    """Return our ARK from external_ark_url if present, configured, and valid."""
    external_ark_url = str(archival_object.get("external_ark_url", "")).strip()
    if not external_ark_url:
        return None

    our_naan = str(naan).strip()
    if not our_naan:
        logger.warning(
            "⚠️ OUR_NAAN IS NOT CONFIGURED; SKIPPING external_ark_url VALIDATION: %s",
            archival_object.get("component_id", ""),
        )
        return None

    decoded = unquote(external_ark_url)
    # Match both ark:/NAAN/name and ark:NAAN/name forms.
    # TODO determine if existing ARK contains a Qualifier after the Assigned Name
    match = re.search(r"ark:(?:/)?([0-9A-Za-z]+)/([^?#/]+)", decoded)
    if not match:
        logger.warning(
            "⚠️ INVALID external_ark_url FORMAT: %s (%s)",
            archival_object.get("component_id", ""),
            external_ark_url,
        )
        return None

    existing_naan = match.group(1)
    if existing_naan.lower() != our_naan.lower():
        logger.warning(
            "⚠️ external_ark_url HAS A DIFFERENT NAAN THAN OUR_NAAN (%s): %s (%s)",
            existing_naan,
            archival_object.get("component_id", ""),
            external_ark_url,
        )
        return None

    existing_our_ark = f"ark:{existing_naan}/{match.group(2)}"
    logger.info(
        "☑️ OUR ARK FOUND IN external_ark_url: %s (%s)",
        existing_our_ark,
        archival_object.get("component_id", ""),
    )
    return existing_our_ark


def build_ark_identifier(naan: str, shoulder: str = "", blade_length: int = 6) -> str:
    generated_betanumeric_string = generate_betanumeric_string(
        blade_length=blade_length
    )
    check_string = f"{naan}/{shoulder}{generated_betanumeric_string}".lower()
    check_digit = calculate_check_digit(check_string)
    base_name = f"{shoulder}{generated_betanumeric_string}{check_digit}"
    return f"ark:{naan}/{base_name}"


def put_objects(
    bucket_name: str,
    ark: str,
    redirect_location: str,
    metadata: dict,
    s3_client=None,
) -> None:
    s3 = s3_client
    if s3 is None:
        import boto3

        s3 = boto3.client("s3")
    prefix = ark.strip("/")
    escaped_redirect_location = html.escape(redirect_location, quote=True)
    link_text = str(metadata.get("title") or ark)
    escaped_link_text = html.escape(link_text)
    redirect_html = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        "    <title>Redirecting…</title>\n"
        "  </head>\n"
        "  <body>\n"
        f'    <a id="r" href="{escaped_redirect_location}">{escaped_link_text}</a>\n'
        f"    <script>(function(){{var t={json.dumps(redirect_location)};var s=new URLSearchParams(window.location.search).get('_suffix');if(s)t=t.replace(/\\/$/,'')+s;var link=document.getElementById('r');if(link)link.href=t;window.location.replace(t);}})();</script>\n"
        "  </body>\n"
        "</html>\n"
    )
    s3.put_object(
        Bucket=bucket_name,
        Key=f"{prefix}/index.html",
        Body=redirect_html.encode(),
        ContentType="text/html; charset=utf-8",
    )
    s3.put_object(
        Bucket=bucket_name,
        Key=f"{prefix}/info.jsonld",
        Body=json.dumps(metadata, indent=2).encode(),
        ContentType="application/ld+json",
    )


def reserve_ark(
    bucket_name: str,
    naan: str,
    shoulder: str = "",
    blade_length: int = 6,
    max_attempts: int = 100,
    s3_client=None,
) -> str:
    """Reserve and return an ARK.

    Generates and reserves a unique ARK using `naan`/`shoulder`.
    """
    s3 = s3_client
    if s3 is None:
        import boto3

        s3 = boto3.client("s3")

    for _ in range(max_attempts):
        candidate_ark = build_ark_identifier(
            naan=naan,
            shoulder=shoulder,
            blade_length=blade_length,
        )
        key = f"{candidate_ark.strip('/')}/index.html"
        try:
            s3.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=b"",
                ContentType="text/html; charset=utf-8",
                IfNoneMatch="*",
            )
            return candidate_ark
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in {"PreconditionFailed", "412"}:
                continue
            raise
    raise RuntimeError(f"Unable to reserve a unique ARK after {max_attempts} attempts")


def mint_ark(
    bucket_name: str,
    nma: str,
    naan: str,
    redirect_target: str | None = None,
    redirect_domain: str | None = None,
    title: str = "",
    creator: str = "",
    date: str = "",
    shoulder: str = "",
    blade_length: int = 6,
    s3_client=None,
    max_attempts: int = 100,
) -> str:
    if (redirect_target is None) == (redirect_domain is None):
        message = "❌ PROVIDE EXACTLY ONE OF redirect_target OR redirect_domain"
        logger.error(message)
        raise ValueError(message)

    resolved_ark = reserve_ark(
        bucket_name=bucket_name,
        naan=naan,
        shoulder=shoulder,
        blade_length=blade_length,
        max_attempts=max_attempts,
        s3_client=s3_client,
    )

    redirect_location = ""
    if redirect_target is not None:
        redirect_location = redirect_target
    elif redirect_domain is not None:
        redirect_location = (
            f"https://{redirect_domain.rstrip('/').split('/')[-1]}/{resolved_ark}"
        )

    metadata = json.loads(
        format_metadata(
            nma=nma,
            ark=resolved_ark,
            title=title,
            creator=creator,
            date=date,
        )
    )

    put_objects(
        bucket_name=bucket_name,
        ark=resolved_ark,
        redirect_location=redirect_location,
        metadata=metadata,
        s3_client=s3_client,
    )
    return resolved_ark
