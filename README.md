# 2340_project_3 — DisasterBot (RAG chatbot)

## Setup
```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # staff users get Knowledge Base / Monitoring pages
python manage.py runserver
```

## Apps
- `chat` — home/about, chat UI, RAG pipeline (`rag.py`), intent-based prompts (`prompts.py`)
- `knowledge` — documents + chunks, ingestion (file / URL / text), cleaning, clear & reload
- `monitoring` — query logs, latency/failure dashboard, accuracy evaluation
- `accounts` — signup / login / logout
