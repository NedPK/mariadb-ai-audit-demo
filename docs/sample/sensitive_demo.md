# Sensitive Retrieval Demo (Do Not Use in Production)

This file exists only to demo compliance behavior:

- MariaDB can retrieve sensitive chunks via vector search
- the application layer blocks exposing them to the LLM (DLP-on-send)

Unique demo keyword: DEMO_SENSITIVE_PRIVATE_KEY_WIDGET

DEMO_DLP_BLOCK_MARKER__NOT_A_REAL_SECRET__DO_NOT_USE

If you can retrieve this chunk, your audit trail should show that exposure was blocked.
