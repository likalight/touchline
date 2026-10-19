# Security

Please report vulnerabilities privately through GitHub's **Report a vulnerability** (Security tab), not in public issues. We aim to respond within five working days.

Touchline is built to run without API keys: Azure services authenticate with a managed identity, producer tools sit behind Microsoft Entra ID roles, and fan questions pass Azure AI Content Safety Prompt Shields. See [docs/GOVERNANCE.md](docs/GOVERNANCE.md).
