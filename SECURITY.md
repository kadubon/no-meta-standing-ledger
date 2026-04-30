# Security Policy

## Supported Versions

Security fixes are provided for the current `main` branch until formal releases
begin. After the first release, supported versions will be documented here.

## Reporting A Vulnerability

Do not open public issues for vulnerabilities that may expose private data,
secrets, or exploit details. Use GitHub private vulnerability reporting if
enabled for the repository. If it is not enabled yet, contact the maintainers
through a private channel listed on the repository profile.

Please include:

- affected version or commit;
- reproduction steps using synthetic data;
- expected and actual behavior;
- whether local files, secrets, or private ledgers may be exposed.

## Scope

In scope:

- accidental export of local paths, secrets, or private evidence content;
- replay divergence from identical public logs;
- bypasses of public event validation;
- unsafe GitHub Actions permissions in this repository.

Out of scope:

- claims that are scientifically incorrect but faithfully represented as public
  standing records;
- third-party evidence URLs controlled outside this project;
- denial of service from intentionally huge local ledgers unless it bypasses
  documented limits.

