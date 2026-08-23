# pi-bridge installed

The Hermes plugin is installed and enabled in the current profile. The external `pi` CLI is a separate dependency.

1. Check whether pi is already available:

   ```bash
   pi --version
   ```

2. If it is missing, install the current package:

   ```bash
   npm install -g --ignore-scripts @earendil-works/pi-coding-agent
   ```

3. Configure/authenticate pi using pi's own supported setup. Do not copy API keys into this repository or Hermes plugin settings.

4. Optionally configure this Hermes profile's Pi cost/model tiers under:

   ```text
   plugins.entries.pi-bridge.settings
   ```

   The semantic tiers are `fast`, `standard`, and `deep`. Provider/model fields may remain blank to use pi's own default. Run `pi_check` after restart to inspect the effective routing.

5. If this profile will use persistent Pi RPC sessions from Telegram/Discord/Slack or another messaging gateway, explicitly grant background completion injection:

   ```bash
   hermes config set plugins.entries.pi-bridge.allow_gateway_injection true
   ```

   This grant is not needed for ordinary synchronous `pi_task` use and should not be enabled automatically.

6. Restart the Hermes session, then ask Hermes to run `pi_check`.

7. Invoke the orchestration convention naturally, for example:

   ```text
   通过 pi_flow 去完成这个目标
   ```

The plugin bundles the skill as `pi-bridge:pi-flow`; Hermes loads it when an explicit `pi_flow` request is detected.

## Profiles

Plugins and their settings are profile-scoped in Hermes. Install/enable this plugin in the profile that should use it.

A dedicated profile is useful when you want a separate long-lived specialist with its own memory, SOUL, model defaults, plugin settings, skills, sessions, and terminal cwd. It is not required for ordinary `pi_flow` requests, and a profile by itself is not a filesystem sandbox.

For a dedicated specialist profile, put the standing specialization in that profile's `SOUL.md`; then the user can state the goal normally while the profile defaults to `pi-bridge:pi-flow` for hands-on work.
