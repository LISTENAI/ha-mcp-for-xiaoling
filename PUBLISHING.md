# GitHub and HACS publishing notes

This repository contains a Home Assistant custom integration and is distributed through HACS.

## Before the first public release

1. Create a public GitHub repository for this project.
2. Replace the placeholder owner, documentation URL, and issue tracker URL in `custom_components/xiaoling_mcp/manifest.json`.
3. Enable Issues and add a short repository description and useful topics on GitHub.
4. Push the repository and wait for the `Validate` and `Tests` workflows to pass.

## Install before HACS default listing

In HACS, add the public GitHub repository as a custom repository and select `Integration` as its type. This makes the integration installable before it is included in the HACS default catalog.

## Create a release

1. Update the `version` in `custom_components/xiaoling_mcp/manifest.json`.
2. Push the change and confirm that validation and tests pass.
3. Open GitHub Actions and run the `Release` workflow on the intended branch.
4. Enter the manifest version without the `v` prefix, for example `0.2.1`.
5. The workflow verifies the manifest, runs the tests and HACS validation, then creates the full GitHub Release `v0.2.1`.

Do not create a release for a version that does not match `manifest.json`. HACS uses the latest full GitHub Release as the published version; creating only a tag is not enough.

## HACS default catalog

After the first release and successful validation, submit the repository to the `integration` list in [`hacs/default`](https://github.com/hacs/default). HACS reviews this separately from the repository CI. Until that pull request is merged, users must install the repository as a custom repository.
