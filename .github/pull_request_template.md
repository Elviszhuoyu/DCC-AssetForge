## Summary

Describe the problem and the smallest change that solves it.

## Scope and compatibility

- Affected hosts/contracts:
- Compatibility identifiers changed: no / yes (explain)
- Product scope expanded: no / yes (link issue)

## Verification

- [ ] `python -m compileall -q asset_forge integrations scripts tests`
- [ ] `python -m unittest discover -s tests -p "test_*.py"`
- [ ] `python scripts/check_repository_hygiene.py`
- [ ] `git diff --check`
- [ ] Real host version and evidence listed below, or explicitly marked unverified

Host evidence or unverified boundary:

## Safety and licensing

- [ ] No credentials, private paths, proprietary assets, engine binaries, generated reports, or restricted code were added
- [ ] New dependencies and copied/generated/reference-derived code are identified with their licenses
- [ ] Fixtures and dry runs are not presented as real host or visual acceptance
