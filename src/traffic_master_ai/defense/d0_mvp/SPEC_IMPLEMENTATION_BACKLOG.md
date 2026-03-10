# D0-MVP Residual Backlog

Spec-defined implementation gaps are closed. Remaining work is operational hardening, not SSOT coverage:

1. Live credential validation
- Scope: offline OpenAI-compatible caller path
- Remaining work: run with real API credentials in a network-enabled environment and confirm provider payload compatibility.

2. Deployment auth integration
- Scope: admin/operator routes
- Remaining work: replace local role+token access control with deployment authn/authz middleware in deployment.

3. Warehouse scale-up
- Scope: local JSONL warehouse
- Remaining work: swap local warehouse for Postgres/ClickHouse when production throughput requires it.
