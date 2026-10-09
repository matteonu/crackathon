# Document engine

`pdf.py` owns PDF validation, extraction, sampling, and rendering. `llm.py` owns the model client and prompts. `engine.py` coordinates contexts, feedback, modes, validation, and deduplication. `anki.py` owns only `.apkg` serialization. `models.py` contains shared types.

Keep these layers one-way: HTTP may call the engine; the engine may call PDF, LLM, and exporters; PDF and Anki must not call the model or Flask.

Current scope is PDF → Quick/Deep processing → five examples → general feedback → final flashcards → `.apkg`. Learner analytics, social competition, review sessions, and graphical exploration are intentionally out of scope.

Future exercises should add a `type` value to `Exercise` and a validator/exporter without changing document-context creation. Learner/expert and exam/exercise modes belong in generation/review context and prompt policy. Performance belongs in a separate review-attempt persistence layer; social features in a session/leaderboard service; graphical exploration in a visual-indexing layer reusing `DocumentPage` text and images.
