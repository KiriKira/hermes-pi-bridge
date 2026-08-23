---
name: pi-reverse-engineering-flow
description: Orchestrate pi for authorized reverse engineering, especially mobile-app-to-local-IoT interoperability and Home Assistant integration
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [pi, reverse-engineering, iot, android, ios, ghidra, jadx, frida, mitmproxy, wireshark, home-assistant]
    requires_tools: [pi_task, pi_session_start, pi_session_send, pi_session_read, pi_session_wait, pi_session_stop]
    related_skills: [pi-bootstrap, pi-task-delegation, pi-interactive-session]
---

# Pi Reverse-Engineering Flow

## Purpose

Use Hermes as the supervisor and pi as the execution worker for authorized reverse engineering. This flow is optimized for the case where an official mobile app controls an IoT device through a vendor cloud and the goal is to discover a legitimate local-only interoperability path, build a protocol PoC, and eventually integrate it with Home Assistant.

## Authorization boundary

Proceed only for software, devices, accounts, traffic, and networks the user owns or is explicitly authorized to test.

Allowed goals include interoperability, local control, migration away from a cloud dependency, protocol documentation, compatibility testing, and defensive analysis.

Do not turn captured credentials, tokens, or keys belonging to other users into reusable artifacts. Do not broaden testing beyond the authorized target/network.

## Supervisor/worker split

Hermes owns:

- target and authorization scope;
- experiment design;
- task decomposition;
- model-tier choice and escalation;
- cross-source reasoning;
- judging evidence quality;
- deciding the next hypothesis;
- final protocol and HA architecture.

Pi owns:

- terminal-heavy exploration;
- JADX/apktool/Ghidra/Frida/adb work;
- pcap/log extraction;
- scripts and parsers;
- controlled experiments;
- protocol PoCs and tests;
- maintaining the project evidence files.

Do not fill Hermes' context with bulk decompiler output when pi can summarize it into evidence files.

## Model routing

Before starting, read `~/.hermes/pi-bridge-models.yaml` if present.

Use semantic tiers:

### fast

Use for high-volume, low-ambiguity tasks:

- file inventory, strings and symbol searches;
- JADX grep/search and candidate-class triage;
- manifest/resource inspection;
- pcap filtering and field extraction;
- endpoint/topic/port inventories;
- converting logs to tables;
- updating notes and protocol field lists.

### code

Use for implementation-heavy tasks:

- Frida hooks;
- mitmproxy addons;
- tshark/scapy helpers;
- binary/packet parsers;
- crypto reproduction after parameters are known;
- Python protocol clients;
- test harnesses;
- Home Assistant integration code.

### deep

Reserve for tasks where reasoning quality matters more than throughput:

- unknown protocol state machines;
- key derivation or session establishment;
- obfuscated control flow;
- native <-> Java/Kotlin/Swift <-> network correlation;
- conflicting captures or hypotheses;
- identifying why a previously plausible local-control theory failed;
- deciding the next experiment after multiple dead ends.

### Escalation contract

Start with the cheapest suitable tier. A pi worker should report:

```text
CONFIDENCE: high|medium|low
FINDINGS:
- ...
EVIDENCE:
- file/function/packet/timestamp references
OPEN_QUESTIONS:
- ...
BLOCKERS:
- ...
RECOMMENDED_NEXT_STEP:
- ...
REQUEST_ESCALATION: none|code|deep
```

Hermes—not pi—decides whether to escalate.

## Workspace layout

At the beginning of a project, create or normalize:

```text
research/
  scope.md
  architecture.md
  observations.md
  hypotheses.md
  protocol.md
  crypto.md
  timeline.md
  decisions.md
  captures/
  apk/
  native/
  hooks/
  scripts/
  poc/
  ha/
```

`scope.md` must record what is authorized and what is out of scope.

`protocol.md` should maintain these sections even before they are understood:

```text
Discovery
Transport
Endpoints / ports / topics
Handshake
Authentication
Session establishment
Packet framing
Serialization
Encryption / integrity
Commands
State responses
Sequence numbers / nonces
Error handling
Reconnect behavior
Unknown fields
Local-only viability
```

## Phase 0 — Establish scope and observability

Before reverse engineering, record:

- exact device model/firmware;
- official app package/version;
- Android/iOS and test-device state;
- whether the phone and IoT device share a LAN/VLAN;
- whether Internet access can be independently blocked for phone/device;
- available capture points;
- whether rooted/jailbroken instrumentation is available;
- Home Assistant target environment.

Do not begin by assuming MITM is required.

## Phase 1 — Black-box network baseline

Goal: determine whether any local data plane already exists.

Create a synchronized timeline for actions such as:

- app launch;
- device discovery;
- read status;
- power on/off;
- change one setting at a time;
- reconnect app;
- block phone Internet only;
- block IoT Internet only;
- block both while keeping LAN connectivity.

Capture where authorized:

- phone <-> LAN;
- IoT <-> LAN;
- phone <-> Internet;
- IoT <-> Internet.

Classify observed paths:

1. direct LAN control;
2. local discovery + cloud command;
3. cloud-issued token/key + local command;
4. device persistent cloud MQTT/WebSocket;
5. BLE bootstrap + LAN control;
6. no observable local control.

Promote concrete packet/timestamp evidence into `timeline.md` and `architecture.md`.

## Phase 2 — Mobile app static analysis

For Android, begin with APK inventory/JADX before native RE.

Search for concepts such as:

```text
DatagramSocket
Socket
OkHttp
WebSocket
Mqtt
BluetoothGatt
NsdManager
MulticastLock
SSLSocket
TrustManager
CertificatePinner
AES
GCM
CBC
HMAC
nonce
localKey
deviceKey
secret
token
protobuf
parseFrom
toByteArray
```

Identify candidate layers:

- discovery;
- transport;
- serializer/codec;
- crypto;
- device repository/manager;
- cloud API client;
- native SDK boundary.

Hermes should ask pi for a call-path summary with file/class/function evidence rather than bulk source dumps.

## Phase 3 — Dynamic instrumentation

Use dynamic observation to validate static hypotheses.

Prefer observing actual runtime values over reconstructing complex logic prematurely. Candidate observations include:

- plaintext before encryption;
- ciphertext after encryption;
- nonce/IV;
- key identifier or derived key material on the user's own device/account;
- serialized protobuf/JSON/CBOR payloads;
- host/port/topic selection;
- LAN/cloud transport branch decisions;
- device IDs and session counters.

Use Frida/adb/debugger instrumentation only within authorized scope.

Record function names, timestamps, inputs/outputs, and matching network packets so static/dynamic/network evidence can be correlated.

## Phase 4 — TLS/MITM only when it answers a specific question

Do not treat MITM as the default objective.

Use it when a concrete unresolved question requires observing the user's own app/cloud exchange, for example:

- whether cloud returns a stable local credential;
- MQTT broker/topic discovery;
- protocol version metadata;
- whether cloud merely mirrors status after a local command;
- whether a session token is necessary for local transport.

If certificate pinning blocks observation, first identify the pinning implementation and instrument the user's own test app/runtime in the least invasive way needed for the experiment.

Do not build the final local integration around vendor-cloud credentials if a cloud-independent local path can be established.

## Phase 5 — Native analysis

Escalate to Ghidra/native work when relevant logic crosses into `.so`, framework, or other native components.

Ask pi to focus on evidence-bearing questions:

- function responsible for packet framing;
- key derivation inputs;
- command dispatch table;
- checksum/MAC construction;
- JNI bridge mapping;
- protocol constants/version bytes;
- local-vs-cloud transport selection.

Rename/comment discovered functions in the analysis database when tooling permits and mirror important conclusions into `research/native/` notes.

## Phase 6 — Reproduce the wire protocol

Build the smallest possible local PoC before Home Assistant code.

Target an API conceptually like:

```python
client = DeviceClient(host, credentials_or_pairing_state)
await client.connect()
status = await client.get_status()
await client.turn_on()
```

Requirements:

- no official app in the control path;
- no vendor cloud in the control path for the claimed local mode;
- deterministic packet parsing;
- explicit timeout/retry behavior;
- captured test vectors where safe;
- reproducible test steps.

Validate with multiple independent actions and reconnect cycles.

## Phase 7 — Prove local-only operation

Before declaring success, repeat core operations with vendor Internet access blocked while preserving required LAN connectivity.

Document exactly what still depends on cloud, if anything:

- initial pairing only;
- initial credential acquisition only;
- periodic refresh;
- firmware/update services only;
- nothing.

The goal is evidence, not the label "local".

## Phase 8 — Home Assistant integration

Only after the PoC is stable should pi implement HA-facing code.

Prefer a clean protocol library boundary separated from Home Assistant entities.

Typical structure:

```text
custom_components/<domain>/
  __init__.py
  manifest.json
  config_flow.py
  const.py
  coordinator.py
  diagnostics.py
  sensor.py
  switch.py
  climate.py
```

Choose push vs polling based on observed device behavior, not convenience.

Add diagnostics that redact credentials/secrets.

## Recommended interactive session pattern

For a multi-day RE project, use a persistent pi session in the project root.

Example sequence:

```text
Turn 1: inventory the workspace and create/update research/scope.md and observations.md
Turn 2: analyze captures and classify local vs cloud traffic
Turn 3: inspect the APK for the candidate transport path
Turn 4: write a minimal Frida hook to validate the serializer/encryption boundary
Turn 5: correlate hook output with a packet capture
Turn 6: update protocol.md with only evidence-backed fields
Turn 7: implement a small decoder/encoder and test against captures
Turn 8: run a live local PoC on the authorized device
Turn 9: verify behavior with Internet blocked
Turn 10: only then scaffold the HA integration
```

Hermes must assess each turn before sending the next.

## Evidence rules

Every important claim should be tagged mentally as one of:

- OBSERVED — directly seen in packet/log/runtime/static artifact;
- INFERRED — best explanation of multiple observations;
- HYPOTHESIS — needs an experiment;
- DISPROVED — tested and rejected.

Pi should update `hypotheses.md` rather than silently replacing failed theories.

Do not promote a hypothesis into `protocol.md` as fact without supporting evidence.

## Stop conditions

Pause the RE flow and report to the user when:

- the next step would exceed the authorized target/network;
- a required secret belongs to another user/account;
- the only proposed method depends on destructive device modification not approved by the user;
- repeated evidence shows there is no cloud-independent local data plane and a different hardware/firmware strategy would be required.

## Definition of done

The flow is complete when the repository contains:

1. an evidence-backed architecture of app/cloud/device communication;
2. a documented protocol sufficient for the implemented subset;
3. a reproducible local PoC;
4. proof of what works with Internet blocked;
5. tests/test vectors that do not expose secrets;
6. a Home Assistant integration or a precise implementation plan based on the validated PoC.
