# Security policy

LAMF 2.x receives security fixes on the latest release. Report suspected vulnerabilities privately through GitHub's **Security > Report a vulnerability** flow. If private reporting is unavailable, open an issue containing no exploit, credential, private data, or reproduction detail and ask the maintainer for a private channel.

Do not attach memory databases, exports, operator tokens, instance keys, logs, vaults, or real personal data. Use synthetic fixtures only.

LAMF is a local-first reference implementation, not a production-hardening claim. Its default network boundary is localhost. Operators remain responsible for host security, backups, access control, and review of the selected security profile. The optional LAMF Optimizations repository does not own or modify durable memory and has a separate issue tracker.

We will acknowledge a credible report, investigate it, coordinate remediation and disclosure with the reporter, and avoid promising a fixed timeline before scope is understood.
