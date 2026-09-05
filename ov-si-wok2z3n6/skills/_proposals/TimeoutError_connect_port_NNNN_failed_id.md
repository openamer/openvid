---
description: auto-proposal for recurring error (seen 3x)
---
# Error pattern

TimeoutError: connect port NNNN failed <id>

# Proposed handling
1. Detect this error signature.
2. Retry once with backoff.
3. If persisting, escalate to user with context.
