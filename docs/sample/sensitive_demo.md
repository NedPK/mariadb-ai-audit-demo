# Sensitive Retrieval Demo (Do Not Use in Production)

This file exists only to demo compliance behavior:

- MariaDB can retrieve sensitive chunks via vector search
- the application layer blocks exposing them to the LLM (DLP-on-send)

Unique demo keyword: DEMO_SENSITIVE_PRIVATE_KEY_WIDGET

-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDemoOnlyNotARealKey
-----END PRIVATE KEY-----

If you can retrieve this chunk, your audit trail should show that exposure was blocked.
