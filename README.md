# arkminter

## Overview

**arkminter** is a Python library for minting ARK identifiers and registering redirect and metadata objects in an S3 bucket. It is designed for integration into digital object workflows, such as archival or publication pipelines.

## Main Features

- **ARK Minting:** Generates unique ARK identifiers with a check digit for validation.
- **Atomic Reservation:** Reserves each ARK with an atomic S3 `put_object` call (`IfNoneMatch="*"`) to avoid collisions.
- **S3 Registration:** Creates two objects per ARK:
  - `index.html`: HTML redirect page with JavaScript redirect support and a visible fallback link.
  - `info.jsonld`: JSON-LD metadata for the ARK.
- **Library-Driven Inputs:** Calling applications provide all values directly.
- **Logging:** Configurable logging via a config file or fallback to basic logging.

## Architectural Decisions

- **Explicit Inputs:** Core functions take explicit arguments for minting, metadata, and redirect behavior.
- **Two-Step Flow:** `reserve_ark` handles uniqueness; `put_objects` writes redirect and metadata content.
- **Importable Library:** Designed to be imported and configured from other Python projects.

## Required Inputs

For `mint_ark`, provide:

- `bucket_name`: Name of your S3 bucket.
- `nma`: Resolver authority with scheme omitted (e.g. `resolver.example.org`).
- `naan`: Your ARK NAAN (Name Assigning Authority Number).
- Exactly one redirect option:
  - `redirect_target`: Full target URL for ARK redirection.
  - `redirect_domain`: Domain used to build `https://<domain>/<ark>`.

Optional string inputs:

- `title`
- `creator`
- `date`
- `shoulder`

Optional controls:

- `blade_length` (default `6`)
- `max_attempts` (default `100`)
- `s3_client` (for dependency injection/testing)

## Example Usage

Suppose you want to mint an ARK and register it in your workflow:

```python
import json
import arkminter

# Reserve an ARK key atomically, then write redirect + metadata objects
ark = arkminter.reserve_ark(
  bucket_name="your-resolver-bucket",
  naan="99999",
)
metadata = json.loads(arkminter.format_metadata(
  nma="resolver.example.org",
  ark=ark,
  title="Sample Object",
  creator="Jane Doe",
  date="2025-09-15",
))
arkminter.put_objects(
  "your-resolver-bucket",
  ark=ark,
  redirect_location="https://your-object-url.example.edu",
  metadata=metadata,
)

print("Minted ARK:", ark)
```

Or use the convenience wrapper:

```python
import arkminter

ark = arkminter.mint_ark(
  bucket_name="your-resolver-bucket",
  redirect_target="https://your-object-url.example.edu",
  nma="resolver.example.org",
  naan="99999",
  title="Sample Object",
  creator="Jane Doe",
  date="2025-09-15",
  shoulder="",
)
```
