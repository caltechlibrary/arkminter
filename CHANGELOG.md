# Arkminter Changelog

## 1.0.0

- declare the API stable. No functional change from 0.2.1: this records that Alchemist has been minting production ARKs with this library, so a `0.x` version string -- which conventionally invites breakage at any time -- misstated its actual status. Subsequent breaking changes get a major bump

## 0.2.1

- fix `build_ark_identifier()` minting names ending in `/` (the check digit algorithm can compute `/` since it must also accept it as the naan/name separator, but a minted name must stay betanumeric-only)

## 0.2.0

- add `get_existing_our_ark()` for shared ARK validation logic (previously duplicated in Distillery and Alchemist)
- begin changelog
