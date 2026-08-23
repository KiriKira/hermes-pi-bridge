# pi-bridge installed

Hermes has installed and enabled the plugin. The remaining dependency is the local `pi` coding agent.

## 1. Check pi

```bash
pi --version
```

If `pi` is missing, install the current official package:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

## 2. Configure pi model access

Start pi:

```bash
pi
```

Use `/login` for a supported subscription/API-key provider, or configure Pi through its documented provider mechanism. Do not put API keys in Hermes plugin settings.

## 3. Optional model tiers

The plugin uses Hermes-native settings under:

```yaml
plugins:
  entries:
    pi-bridge:
      settings:
        fast_provider: ""
        fast_model: ""
        fast_thinking: minimal
        standard_provider: ""
        standard_model: ""
        standard_thinking: medium
        deep_provider: ""
        deep_model: ""
        deep_thinking: high
```

Blank provider/model values mean Pi's own configured default. Explicit tool-call overrides still take precedence.

## 4. Verify

Restart Hermes if needed, then use `pi_check` or run:

```bash
hermes plugins doctor pi-bridge --ci
```

The bundled flow skill is namespaced as `pi-bridge:pi-flow`. A user can invoke it naturally by saying, for example:

```text
通过 pi_flow 去完成这个目标
```
