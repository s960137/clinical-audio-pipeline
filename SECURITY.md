# Data and security boundary

This repository contains source code and hand-authored synthetic fixtures only.

## Never publish

- Patient recordings, spreadsheets, names, national IDs, medical records, dates of birth or record-level clinical outputs.
- Identity-to-code maps, ID-derived filenames or screenshots of authenticated clinical pages.
- Credentials, cookies, browser profiles, private service URLs, signed download URLs or raw logs.
- The original research repository's history, even if sensitive files were deleted in its latest version.

Opaque identifiers are pseudonyms, not proof of anonymization. Date/time linkage, audio, manifests, cache metadata and input hashes can remain sensitive. Generated runtime files are ignored by Git, but a user can override ignore rules: always inspect the staged tree before publishing.

## Network behavior

The core demo binds to loopback only and serves generated data. The downloader requires explicitly allowed hosts, HTTPS for external sources, finite retries and response-size limits. It rejects redirects. API tokens stay in memory and are attached only to the configured HTTPS origin, including its port. Other allowed download hosts do not receive that token. No stored browser sessions are included.

Run only against systems and records you are authorized to access. Host allowlisting does not establish authorization. The browser adapter is site-specific and must be reviewed and configured locally. It requires a browser and potentially a driver download when first used.

## File behavior

The pipeline requires a new output directory, never rewrites source tables, and keeps downloaded duplicate assets. It records exclusions instead of deleting recordings. Interrupted runs remain available for inspection. Do not run concurrent writers against the same output or cache directory.

The CLI deliberately suppresses raw exception details because third-party exceptions can embed source URLs, local paths or server responses. Download outcomes use short reason codes; schema and configuration failures return a nonzero exit status. Use synthetic reproductions for debugging.

## Reporting

For a code defect, open a GitHub issue using fictional inputs. Never attach real patient files, tokens, signed URLs or authenticated screenshots. For a suspected data exposure, avoid posting the sensitive content publicly; revoke any affected credential through its issuer and contact the repository owner privately through an established channel.

The staged-file scan is a defense-in-depth check, not an anonymization or compliance certification.
