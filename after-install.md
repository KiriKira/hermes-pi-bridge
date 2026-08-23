# pi-bridge installed

The Hermes plugin is installed. The external `pi` CLI is a separate dependency.

1. Check whether pi is already available:

   ```bash
   pi --version
   ```

2. If it is missing, install the current package:

   ```bash
   npm install -g --ignore-scripts @earendil-works/pi-coding-agent
   ```

3. Configure/authenticate pi using pi's own supported setup. Do not copy API keys into this repository or Hermes plugin settings.

4. Restart the Hermes session, then ask Hermes to run `pi_check`.

5. Invoke the orchestration convention naturally, for example:

   ```text
   通过 pi_flow 去完成这个目标
   ```

The plugin bundles the skill as `pi-bridge:pi-flow`; Hermes loads it automatically when an explicit `pi_flow` request is detected.

## Profiles

Plugins are profile-scoped in Hermes. Install/enable this plugin in the profile that should use it. A dedicated profile is useful only when you want a separate long-lived agent identity/state (different memory, model defaults, skills, terminal cwd, etc.); it is not required for ordinary `pi_flow` requests.
