# hermes-pi-bridge

A robust Hermes Agent plugin designed to bridge the gap between the high-level reasoning of Hermes and the deep, iterative coding capabilities of the `pi` coding agent.

This bridge enables Hermes to delegate complex, multi-step engineering tasks to `pi`, which operates in a dedicated environment with full access to filesystem and shell tools.

## 🚀 Features

- **Hybrid Execution Models**: Supports both synchronous one-shot tasks (`pi_task`) and asynchronous, long-running interactive sessions (`pi_session_*`).
- **RPC-based Communication**: Uses a highly reliable JSON-RPC protocol over stdin/stdout, providing explicit completion signals and avoiding the pitfalls of idle-timeout detection.
- **Stateful Interactive Sessions**: Maintains conversation context and filesystem state across multiple turns, allowing for deep, iterative debugging and development.
- **Built-in Task Management**: Tracks the status, duration, and model information for all active and completed tasks.
- **Hermes Native Integration**: Designed as a first-class Hermes plugin, providing a seamless toolset for the agent to use during complex workflows.

## 🛠 Toolset

The plugin provides a comprehensive suite of tools:

### One-Shot Tasks
- `pi_task`: Run a single coding task and block until completion.
- `pi_task_async`: Kick off a task in the background and receive notification upon completion.
- `pi_task_status`: Inspect the status of ongoing or past tasks.
- `pi_task_result`: Retrieve the full output and metadata of a completed task.
- `pi_check`: Verify `pi` installation and environment configuration.

### Interactive Sessions
- `pi_session_start`: Initialize a persistent, interactive RPC session.
- `pi_session_send`: Send a new prompt to an active session.
- `pi_session_read`: Read the accumulated output and event history from a session.
- `pi_session_wait`: Block until the current turn in a session is complete.
- `pi_session_stop`: Gracefully terminate an active session.
- `pi_session_list`: View all active and historical sessions.

## 📦 Installation

1. **Install `pi` coding agent**:
   ```bash
   npm install -g @mariozechner/pi-coding-agent
   ```

2. **Clone this repository**:
   ```bash
   git clone https://github.com/szabo-agent/hermes-pi-bridge.git
   cd hermes-pi-bridge
   ```

3. **Run the installer**:
   The installer will symlink the plugin and skills into your `~/.hermes` directory and update your `config.yaml`.
   ```bash
   ./install.sh
   ```
   *(Use `./install.sh --force` to overwrite existing symlinks/files)*

4. **Restart Hermes**:
   Restart your Hermes Agent instance to load the new plugin and toolset.

## 📂 Project Structure

- `plugin/`: The core Python implementation of the Hermes plugin.
- `skill/`: Documentation and usage patterns for the Hermes skills provided by this plugin.
- `install.sh`: Automated installation script.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---
*Developed for the Hermes Agent ecosystem.*
