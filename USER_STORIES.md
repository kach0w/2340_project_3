# User Stories

> **Disclaimer:** The End User persona and customized user stories were delivered by the team as part of their midterm part b assignment.

## End User

1. As an **End User**, I want to access the chatbot through a hosted web application, so I can interact with it from anywhere.
2. As an **End User**, I want to ask natural language questions about the selected topic, so I can receive relevant information.
3. As an **End User**, I want responses to be grounded in the provided dataset, so I can trust their accuracy.
4. As an **End User**, I want to see which documents or sources were used to generate an answer, so I can verify the response.

## Developer

5. As a **Developer**, I want to define and update the dataset used by the RAG system, so the chatbot's knowledge stays current.
6. As a **Developer**, I want to ingest data using at least two distinct ingestion methods (e.g., API-based ingestion, document scraping, or direct text/file uploads) so I can build a rich and flexible knowledge base.
7. As a **Developer**, I want to clean and preprocess data before ingestion, so retrieval results are accurate and relevant.
8. As a **Developer**, I want the system to dynamically select or construct prompts based on the type of user question, so I can control the chatbot's behavior for different intents (e.g., factual lookup vs. explanation vs. creative response).
   - *Prompt behavior **must** be determined programmatically at runtime; manually editing a single static prompt string is not sufficient.*
9. As a **Developer**, I want to test response accuracy against known questions, so I can validate system correctness.

## Administrator

> **Note:** For the administrator user stories, these must be functionalities on the website itself, not only the cloud console.

10. As an **Administrator**, I want to monitor system performance (latency, failures), so the chatbot meets responsiveness requirements.
11. As an **Administrator**, I want to manually clear or reload the chatbot's knowledge base so I can recover from incorrect or outdated data.
12. As an **Administrator**, I want to view basic usage logs (e.g., number of queries, timestamps, response times) so I can understand how the chatbot is being used.

---

## Implementation status

| # | Status | Where | What's left |
|---|---|---|---|
| 1 | 🟡 | whole Django app | Not deployed yet |
| 2 | 🟡 | `chat/views.py`, `chat/rag.py` | `generate()` is a stub, so no LLM is hooked up |
| 3 | 🟡 | `chat/prompts.py` (`SYSTEM_PROMPT`) | Grounding prompt exists, but needs the LLM and better retrieval (embeddings) |
| 4 | ✅ | `chat/templates/chat.html` | — |
| 5 | ✅ | `knowledge/models.py`, `/knowledge/` | — |
| 6 | ✅ | `knowledge/ingestion.py` (file, URL, text) | Optional: PDF and API ingestion |
| 7 | 🟡 | `clean_text`, `chunk_text` | Cleanup is basic; embeddings aren't computed |
| 8 | ✅ | `chat/prompts.py` | Optional: classifier-based intent detection |
| 9 | 🟡 | `monitoring/evaluation.py`, `/monitoring/evaluation/` | Scoring is keyword-only |
| 10 | ✅ | `/monitoring/` dashboard | — |
| 11 | ✅ | `/knowledge/` clear/reload buttons | — |
| 12 | ✅ | `/monitoring/logs/` | — |
