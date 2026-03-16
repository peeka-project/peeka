---
layout: default
title: AI Agent Skill
nav_order: 7
permalink: /ai-skill
---

# AI Agent Skill
{: .no_toc }

Teach your AI coding assistant to diagnose Python applications using Peeka.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## What is peeka-diagnostics

`peeka-diagnostics` is an **AI Agent skill file** (SKILL.md). Once installed, your AI coding assistant (OpenCode, Cursor, Cline, etc.) can:

- **Auto-diagnose**: Choose the right peeka commands based on observed symptoms (slow requests, memory leaks, deadlocks, etc.)
- **Execute diagnostics**: Attach to running Python processes via `peeka-cli` and collect data in real time
- **Parse results**: Analyze structured JSONL output using `jq` pipelines
- **Follow playbooks**: Apply built-in diagnostic workflows (performance, exceptions, memory, threads)

The skill covers all 14 Peeka CLI commands with complete flag references, jq recipes, condition expression syntax, and safety protocols.

---

## Skill Contents Overview

### Diagnostic Decision Tree

The skill includes a symptom-to-command mapping table. The AI automatically selects the right diagnostic path:

| Symptom | Recommended Commands | Goal |
|---------|---------------------|------|
| Slow response / high latency | `watch` → `trace` | Find the slow sub-call |
| Wrong return value / logic bug | `watch` to observe I/O | Correlate inputs to outputs |
| Exception / unexpected error | `watch -e` → `stack` | Find where and why the exception occurs |
| High memory / memory leak | `memory` command suite | Find what allocates and holds memory |
| High CPU | `top` → `trace` | Find CPU-intensive code paths |
| Deadlock / hang | `thread` → `stack` | Find lock contention points |

### 4 Diagnostic Playbooks

| Playbook | Scenario | Core Flow |
|----------|----------|-----------|
| A: Performance | Slow APIs, high latency | watch for slow calls → trace call tree → pinpoint bottleneck |
| B: Exceptions | Production errors | watch -e to capture → stack for context → root cause analysis |
| C: Memory | Growing memory usage | memory start tracking → snapshots → diff → referrers trace |
| D: Threads | Deadlocks, stuck threads | thread list states → filter WAITING → stack inspection |

### JSONL Parsing

All CLI output is JSONL. The AI uses `jq` for structured analysis:

```bash
# Filter slow calls
peeka-cli watch "module.func" -n 10 | jq 'select(.type == "observation" and .cost > 100)'

# Extract exception info
peeka-cli watch "module.func" -e -n 5 | jq 'select(.success == false) | {func: .func_name, error: .exception}'

# Memory top analysis
peeka-cli memory --action top | jq '.data.top_allocations[:5]'
```

---

## Installation

### Prerequisites

- Peeka installed (see [Installation Guide](/installation))
- An AI coding assistant that supports Skill/SKILL.md files

### Method 1: Project-Level Installation (Recommended)

Copy the skill file into your project's `.agents/skills/` directory:

```bash
# From your project root
mkdir -p .agents/skills/peeka-diagnostics

# Download the skill file from the Peeka repository
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

Resulting directory structure:

```
your-project/
├── .agents/
│   └── skills/
│       └── peeka-diagnostics/
│           └── SKILL.md
├── src/
│   └── ...
└── ...
```

### Method 2: Global Installation

If your AI tool supports a global skills directory (e.g., `~/.config/opencode/skills/`):

```bash
mkdir -p ~/.config/opencode/skills/peeka-diagnostics
curl -o ~/.config/opencode/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

---

## Usage

### OpenCode

Load the skill via `load_skills` in OpenCode:

```typescript
task(
  category="deep",
  load_skills=["peeka-diagnostics"],
  prompt="My API is slow, diagnose PID 12345 with peeka"
)
```

Or reference it directly in conversation:

```
@peeka-diagnostics My Python service memory keeps growing, PID 54321, help me investigate
```

### Other AI Tools

For Cursor, Cline, or other AI tools with custom instruction support:

1. Ensure the skill file is at `.agents/skills/peeka-diagnostics/SKILL.md`
2. The AI tool will auto-discover and load the skill
3. When you describe Python diagnostic problems, the AI will apply the skill's knowledge

### Trigger Keywords

These keywords activate the peeka-diagnostics skill:

- `debug python`, `diagnose python`
- `slow app`, `memory leak`, `high CPU`
- `trace function`, `watch expression`
- `thread deadlock`, `runtime debugging`
- `profile python`, `peeka`

---

## Example Scenarios

### Scenario 1: Slow API Endpoint

> "My /api/users endpoint went from 50ms to 2s response time, target process PID is 12345"

The AI will automatically:
1. `peeka-cli attach 12345`
2. `peeka-cli sc "*user*"` to discover relevant classes
3. `peeka-cli watch "myapp.api.users.get_users" -n 5 --condition "cost > 100"` to filter slow requests
4. `peeka-cli trace "myapp.api.users.get_users" -n 3 -d 5` to break down the call tree
5. Analyze JSONL output and pinpoint the bottleneck sub-function
6. `peeka-cli reset && peeka-cli detach` to clean up

### Scenario 2: Memory Leak

> "My Python service memory grew from 200MB to 2GB after a few hours, PID 54321"

The AI will automatically:
1. Attach and start tracemalloc tracking
2. Take multiple snapshots at intervals and diff them
3. Use `memory --action top` to find the largest allocation sources
4. Use `memory --action referrers` to trace reference chains
5. Output analysis report with fix recommendations

### Scenario 3: Thread Deadlock

> "My service is stuck, all requests are timing out, PID 33333"

The AI will automatically:
1. `peeka-cli thread` to list all thread states
2. Filter threads in `WAITING` state
3. Get detailed stack traces for suspect threads
4. Analyze lock contention and provide recommendations

---

## Maintaining the Skill

### Updating

When Peeka releases a new version, update the skill file:

```bash
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

### Custom Extensions

The skill file is plain Markdown — extend it to fit your project:

- Add project-specific diagnostic patterns
- Add shortcuts for commonly-watched function patterns
- Supplement with project-specific troubleshooting steps

---

## FAQ

### AI doesn't use peeka for diagnostics?

- Confirm the skill file is correctly installed at `.agents/skills/peeka-diagnostics/SKILL.md`
- Use Python diagnostic keywords explicitly in your prompt
- Verify `peeka-cli` is installed and accessible

### AI diagnostic commands fail?

- Check Peeka installation: `peeka-cli --help`
- Confirm the target process is still running: `ps -p <pid>`
- Check permissions (ptrace_scope, CAP_SYS_PTRACE)

### Where can I find the skill file?

- **GitHub repository**: [peeka/.agents/skills/peeka-diagnostics/SKILL.md](https://github.com/wwulfric/peeka/tree/master/.agents/skills/peeka-diagnostics)
- **Raw download URL**: `https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md`
