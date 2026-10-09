PDF TO QUESTIONS AND ANSWERS WITH THE OPENAI API

The script keeps its original filename, pdf_to_anki.py, for compatibility.
It now asks for feedback ONCE and exports questions.json. It does not create
Anki files. Every final question includes an answer.

Setup
  Requires Python 3.10+, pypdf, and openai.
  python -m pip install -r requirements.txt
  Install these packages in your Python environment before running.

  At the very top of pdf_to_anki.py, fill in the string:
  API_KEY = "your-openai-api-key"

  The next settings select your server and model:
  API_BASE_URL = "https://api.openai.com/v1"
  MODEL = "gpt-6-astra"

  Change MODEL or pass --model to choose a compatible model. MAX_OUTPUT_TOKENS is also configurable.
  No Codex executable, Codex login, or genanki package is needed.
  Your key is sent as authentication to the configured API server.
  Your API account's billing and rate limits apply. Never commit your real key.

Run from this folder
  python pdf_to_anki.py "C:\path\to\document.pdf"

  Or, if you created a virtual environment in .venv:
  .\.venv\Scripts\python.exe pdf_to_anki.py "C:\path\to\document.pdf"

  Customize the number of questions and language:
  python pdf_to_anki.py "C:\path\to\document.pdf" --questions 100 --language English

  A legacy --codex option is accepted but ignored, so earlier commands still run.

Workflow
  1. Extract the PDF text with physical page numbers.
  2. Display four example question-and-answer cards for you to assess.
  3. Ask for feedback once. Type your changes and press Enter to submit.
     Press Enter immediately to keep the style; /quit saves progress and exits.
  4. Apply that feedback directly to the full question set, with no additional
     feedback or revised-preview round.
  5. Save questions.json with a questions array of question-and-answer objects.
     Example: {"questions": [{"question": "What is an isolated system?",
                             "answer": "A system that exchanges neither matter nor energy with its surroundings."}]}

  The default is 60 questions. --questions changes the count (minimum 5).
  --cards still works as an alias for --questions, so old run commands work.
  --title names the session in its checkpoint metadata; --deck-name is an alias.
  The five categories still guide generation and are approximately balanced:
    Definition
    High level concept
    Low level concept
    Detail fact knowledge
    Extrapolation/conclusion from concept

Output
  questions_output\questions-<timestamp>-<unique suffix>\questions.json

  Use --output-dir to select a different parent folder. Each session contains
  one final questions.json file and a work subfolder holding the PDF copy,
  extraction, initial Q&A preview, prompts, responses, request metadata, and checkpoints.
  Final batch responses contain questions, answers, and source metadata.
  The final questions.json contains only question and answer fields per item.
  No .apkg file is created. Existing Anki files from older runs are untouched.

Resume
  Add --resume "path\to\questions-<timestamp>-<unique suffix>" to your command.
  Keep the same PDF, count, title, language, and --allow-empty-pages setting.
  Previously entered feedback and completed batches are reused, so feedback
  is not requested again. --timeout and --model may be changed.
  Older questions-only sessions reuse the preview and feedback, then regenerate
  the final set with answers. Their previous checkpoint is backed up first.
  Old Anki-format sessions cannot be resumed; start a new run.

Notes
  - Calls your configured server with the OpenAI SDK and API_KEY string. It reuses
    one HTTPS client across requests and never starts a local Codex process.
    Internet access and API access to the configured model are required.
  - Each request prints its elapsed time. Metadata files contain token usage,
    timing, and status. The script does not put API keys in prompts or logs.
  - Network, quota, and authentication errors stop promptly with progress saved.
    SDK retries are disabled; invalid card data gets one correction attempt.
  - Requests use store=False and a strict JSON schema. Local work files still
    contain source text and previews so the script can resume.
  - Extracted PDF text is sent as API input. Images and diagrams
    are not interpreted. Scanned PDFs need OCR first.
  - Pages without extractable text stop the run by default. Use
    --allow-empty-pages only if those pages may be omitted.
  - Final generation combines adjacent text sections into larger requests and
    generates up to 60 questions per request. All extracted text is retained.
    The terminal shows the planned request count before asking for feedback.
    Very large PDFs still use multiple requests; previews sample sections.
    Old sessions with completed batches retain their original batch layout.
  - The script checks counts, categories, page references, empty fields, and
    exact normalized duplicate questions. Review generated questions for quality.
  - All batches must validate before the final questions.json is written.
  - Diagnostic logs and checkpoints contain your PDF text and generated answers.

More options
  python pdf_to_anki.py --help

API references
  https://developers.openai.com/api/docs/guides/structured-outputs
  https://developers.openai.com/api/docs/models/gpt-5.4-mini

The committed script contains an empty API_KEY template.

PDF abstracts
  pdf_summaries.py creates a single JSON containing one abstract per input PDF.
  It reuses this script's API settings. See README_summaries.txt for examples.
  python pdf_summaries.py "first.pdf" "second.pdf" --words 200
