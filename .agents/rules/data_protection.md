# SafeVault Data Protection & Zero Data Loss Policy

CRITICAL SAFEGUARD FOR VOICE CADDY PRO:

1. **PERMANENT DATA PRESERVATION**:
   - Never delete, truncate, overwrite, or reset user databases or data files:
     - `voice_caddy/voice_caddy.db` (and `.db.bak`)
     - `voice_caddy/data/users.json`
     - `voice_caddy/data/profiles/*.json` (all player handicaps, bag clubs, ball preferences)
     - `voice_caddy/data/telegram_config.json` and `telegram_users.json`
   - All code updates, bug fixes, refactoring, and style improvements MUST preserve existing files and rows intact.

2. **TEST ISOLATION**:
   - Unit tests and automated suites MUST NEVER execute against the production `voice_caddy.db` or `voice_caddy/data/` files. Always use `tempfile.mkdtemp()` or `:memory:` databases in tests.

3. **SESSION RESILIENCE & LOGIN STABILITY**:
   - Ensure users do not lose their customized profile, handicap, or bag configuration between sessions.
   - Do not force password resets on established members.
