# Security Policy

This project uses automated tools to track vulnerabilities in dependencies and runtime containers. Vulnerability reports are surfaced via CI jobs and GitHub alerts.

## Reporting a Vulnerability

Please open a security advisory via GitHub if you discover a vulnerability. Do not disclose security issues publicly until they are resolved.

## Dependency Audits

Third-party Python packages are scanned with `pip-audit` and Docker images are scanned with Trivy in CI. JavaScript dependencies are handled by `npm audit` during regular builds.

## Dynamic Scanning

Each push to `main` triggers an OWASP ZAP baseline scan against the staging environment (`https://staging.example.com`).
The resulting report is parsed and the workflow fails if any medium or high vulnerabilities are found.

## Mitigation Tracking

All detected vulnerabilities are tracked in GitHub Issues and cross-referenced here once fixed. Document mitigation steps in issue comments or pull request descriptions.
