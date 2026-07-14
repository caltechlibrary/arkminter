# Arkminter Changelog

## 0.2.1

- fix `build_ark_identifier()` minting names ending in `/` (the check digit algorithm can compute `/` since it must also accept it as the naan/name separator, but a minted name must stay betanumeric-only)

## 0.2.0

- add `get_existing_our_ark()` for shared ARK validation logic (previously duplicated in Distillery and Alchemist)
- begin changelog
