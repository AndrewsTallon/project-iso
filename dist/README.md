# dist/ packaging output

This folder contains deterministic packaging outputs for the offline runtime bundle.

## Required package contents
For a given `<version>`, packaging produces:
- `runtime-<version>.tar.gz`
- `runtime-<version>.zip`
- `manifest-<version>.txt` (sorted list of packaged file paths)
- `checksums-<version>.sha256` (SHA-256 for package artifacts and manifest)
- `version-<version>.json` (version metadata)

## Build command
```bash
runtime/bin/package-dist <version>
```

The packager uses normalized ordering and metadata (`tar --sort=name`, fixed mtime/owner, sorted zip input) so output content and archive layout are deterministic for the same input tree.
