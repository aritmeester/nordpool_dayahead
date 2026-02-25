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
2. Update user-facing documentation when behavior/entities/services changed
   - at minimum verify and update `README.md` for changed timings, sensors, attributes and examples
3. Update version in `custom_components/nordpool_dayahead/manifest.json`
   - example: `"version": "2026.1.1"`
4. Commit the changes
5. Create an annotated tag matching the version with `v` prefix
6. Push `main` and the tag
7. GitHub Actions release workflow creates the GitHub Release
   - release body is automatically taken from `CHANGELOG.md` section `## [vYYYY.MINOR.PATCH] - YYYY-MM-DD`

## Release notes policy (important)

The GitHub Release description must match `CHANGELOG.md` for the same version tag.

- The workflow now enforces this by extracting the matching changelog section based on the pushed tag.
- If a matching section is missing, the release job fails.
- This keeps HACS/GitHub users aligned with the documented changes.

## Commands

```powershell
# 1) Update CHANGELOG.md, README.md (if needed) and manifest.json first

# 2) Commit
git add CHANGELOG.md README.md custom_components/nordpool_dayahead/manifest.json
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
- Ensure each release tag has a matching header in `CHANGELOG.md` before pushing the tag.
- Treat README/docs sync as a release gate: do not tag if documented behavior differs from implemented behavior.
