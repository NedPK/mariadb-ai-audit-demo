# MariaDB AI Audit Demo Doc

This is a small demo document for verifying ingestion.

MariaDB Vector lets you store embeddings and run similarity search inside MariaDB.
We will chunk this text, embed the chunks, and store them in the `chunks` table.

If ingestion works, you should see:
- a row in `documents`
- multiple rows in `chunks`

The goal is repeatability and traceability: later we can retrieve relevant chunks for a question.
