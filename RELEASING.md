# Releasing

This project uses **CalVer** with the format:

- `YYYY.MINOR.PATCH` in `manifest.json` (example: `2026.1.0`)
- `vYYYY.MINOR.PATCH` as Git tag (example: `v2026.1.0`)

## Versioning rules

- `YYYY`: release year
- `MINOR`: feature release counter in that year
- `PATCH`: bugfix counter for that minor release

Examples:

- `2026.1.0` first feature release in 2026
- `2026.1.1` bugfix on `2026.1.0`
- `2026.2.0` next feature release in 2026

## Release steps

1. Update `CHANGELOG.md` under `## [Unreleased]`
   - move completed items to a new version section, e.g. `## [v2026.1.1] - 2026-02-23`
2. Update version in `custom_components/nordpool_dayahead/manifest.json`
   - example: `"version": "2026.1.1"`
3. Commit the changes
4. Create an annotated tag matching the version with `v` prefix
5. Push `main` and the tag
6. GitHub Actions release workflow creates the GitHub Release

## Commands

```powershell
# 1) Update CHANGELOG.md and manifest.json first

# 2) Commit
git add CHANGELOG.md custom_components/nordpool_dayahead/manifest.json
git commit -m "Bump version to 2026.1.1"

# 3) Tag
git tag -a v2026.1.1 -m "Release v2026.1.1"

# 4) Push
git push origin main
git push origin v2026.1.1
```

## Notes

- Keep manifest version **without** `v`.
- Keep Git tag **with** `v`.
- If GitHub blocks push due to email privacy, set a GitHub noreply email for git commits.
