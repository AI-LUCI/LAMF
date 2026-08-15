# Security policy

LAMF 3.x receives security fixes on the latest release. LAMF 2.x is superseded.
Report suspected vulnerabilities privately through GitHub's **Security > Report
a vulnerability** flow. If private reporting is unavailable, open an issue
containing no exploit, credential, private data, or reproduction detail and ask
the maintainer for a private channel.

Do not attach memory databases, exports, operator tokens, instance keys, logs, vaults, or real personal data. Use synthetic fixtures only.

LAMF is local-first and defaults to a loopback-only network boundary. Protocol 3
encrypts bodies and metadata at rest and keeps only keyed tokens in its derived
search index. These controls do not replace host security, backups, access
control, or review of the selected security profile. The optional LAMF
Optimizations repository does not own or modify durable memory and has a separate
issue tracker. The verified threat-model changes and remaining boundaries are
documented in [`docs/RELEASE_3_0.md`](docs/RELEASE_3_0.md).

We will acknowledge a credible report, investigate it, coordinate remediation and disclosure with the reporter, and avoid promising a fixed timeline before scope is understood.
