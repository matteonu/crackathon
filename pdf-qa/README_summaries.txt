PDF SUMMARIES

Run pdf_summaries.py from this folder. It reuses API_KEY, API_BASE_URL,
MODEL, and MAX_OUTPUT_TOKENS from pdf_to_anki.py, which must stay beside it.
It uses the same installed dependencies and asks for no feedback.
Rerunning a command skips PDFs already summarized in the selected mode and
appends only missing summaries.

At the beginning of pdf_summaries.py, set:
  DEEP_MODE = False
  False keeps the existing text extraction.
  True sends the complete PDF to the model, including page images at high detail.
  Deep mode reads slide text, diagrams, charts, tables, equations, and images.
  It also accepts scanned or image-only slides without local OCR.
  It requires a PDF vision-capable model/server; OpenAI gpt-6-astra supports it.
  Each PDF must be under 50 MB and unlocked. Very long PDFs can exceed the model's
  context; split them into smaller PDFs if needed. Deep mode can use more tokens.
  There are no additional Python packages to install.

Summarize two PDFs, with 200 words per abstract by default:
  python pdf_summaries.py "C:\path\first.pdf" "C:\path\second.pdf"

Choose the word count and output file:
  python pdf_summaries.py "first.pdf" "second.pdf" --words 300 --output summaries.json

Summarize all PDFs directly inside a folder (not its subfolders):
  python pdf_summaries.py "C:\path\to\pdfs" --words 200

Use the already installed Python environment from Git Bash:
  ./.venv/Scripts/python.exe pdf_summaries.py "first.pdf" "second.pdf" --words 200

Output:
  One UTF-8 JSON file, pdf_summaries.json by default, containing:
  {
    "requested_words": 200,
    "model": "your configured model",
    "summaries": [
      {"file": "first.pdf", "path": "full input path", "abstract": "...", "word_count": 200,
       "requested_words": 200, "model": "your configured model", "language": "English", "deep_mode": false}
    ]
  }

--words is a target from 1 to 5000 per PDF. The script counts whitespace-separated
words and makes at most one short correction request. If the count still differs,
it reports and records the actual count; it never cuts off sentences just to fit.
Hyphenated words count as one. The default language follows each PDF; use
--language English to override it. --model and --timeout can also be changed.

In text mode, every readable page is included. Very long PDFs are summarized in sections and
then combined into one abstract per PDF. Extracted text is sent to your configured
API server. Images and diagrams are not interpreted; scanned PDFs need OCR.
Pages without text stop text mode unless --allow-empty-pages is supplied.
Deep mode sends every page of the original PDF; it does not omit pages without text
and does not use --allow-empty-pages. The API processes PDF text and page images.

If --output does not exist, it is created when the first summary succeeds.
Existing entries are preserved. PDFs are matched by their resolved full path and mode,
so identical filenames in different folders are treated as separate files.
Already summarized paths in the same mode are skipped before extraction or API calls, even if
--words, --model, --language, or the PDF contents have changed. To regenerate,
choose a different --output file or remove that PDF's entry from the JSON.
Changing DEEP_MODE appends a separate summary for that mode. Existing summaries
without a deep_mode field are treated as text-only summaries. Reruns in either
mode skip the matching summary, so toggling modes does not create duplicates.

Each completed summary is saved immediately using an atomic file replacement.
If a later PDF fails, completed summaries remain saved. Rerun the same command
to continue with missing files. Invalid existing JSON is never overwritten.
Existing JSON from older script versions is supported. Top-level settings retain
their original values; new entries record their own word target, model, and language.
No API keys are stored in the JSON. Review summaries for factual accuracy.

API implementation reference:
  https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses
  https://developers.openai.com/api/docs/guides/file-inputs
