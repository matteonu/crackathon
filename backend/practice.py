"""User-scoped persisted sessions around the notebook's pure Python scheduler."""
from copy import deepcopy
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from auth import current_user
import db
from errors import RequestError
from learning.scheduler import Flashcard, FlashcardScheduler

bp = Blueprint('practice', __name__, url_prefix='/api/practice')
RATINGS = ('again', 'hard', 'good', 'easy')
FIELDS = ('maturity', 'n_times_seen', 'n_mistakes', 'lapses', 'ease', 'status', 'learning_step',
          'due', 'last_review', 'successful_streak', 'total_response_seconds', 'timed_reviews')


def load_scheduler(subject_id=None, folder_id=None, deck_id=None, *, user_id=None):
    """Material UUIDs serve as hierarchy keys; stable card IDs map notebook indices to rows."""
    user_id = current_user()['id'] if user_id is None else user_id
    conn = db.get_db()
    materials = {r['id']: r for r in conn.execute(
        'SELECT * FROM materials WHERE user_id=? ORDER BY added_at, id', (user_id,))}
    if deck_id:
        root = materials.get(deck_id)
        if not root or root['kind'] != 'deck':
            raise RequestError(404, 'This deck does not exist.')
        subject_id = root['subject_id']
    if folder_id:
        root = materials.get(folder_id)
        if not root or root['kind'] != 'folder' or (subject_id and root['subject_id'] != subject_id):
            raise RequestError(404, 'This folder does not exist.')
        subject_id = root['subject_id']
    cards_by_deck = {}
    for r in conn.execute('''SELECT c.*,p.* FROM flashcards c JOIN flashcard_progress p
                            ON p.card_id=c.id AND p.deck_id=c.deck_id WHERE p.user_id=?
                            ORDER BY c.position,c.id''', (user_id,)):
        cards_by_deck.setdefault(r['deck_id'], []).append(r)
    mapping, names, weights = {}, {(): 'All flashcards'}, {}

    def deck_node(deck, path):
        rows = cards_by_deck.get(deck['id'], [])
        for position, r in enumerate(rows):
            mapping[path + (position,)] = r
        names[path] = deck['name']
        return [{'question': r['question'], 'answer': r['answer']} for r in rows]

    def folder_node(parent, path, subject):
        node = {}
        for m in materials.values():
            if m['subject_id'] != subject or m['parent_id'] != parent:
                continue
            child = path + (m['id'],)
            if m['kind'] == 'folder':
                names[child] = m['name']
                weights[child] = m['folder_weight']
                node[m['id']] = folder_node(m['id'], child, subject)
            elif m['kind'] == 'deck':
                node[m['id']] = deck_node(m, child)
        return node

    if deck_id:
        collection = deck_node(materials[deck_id], ())
    elif subject_id:
        collection = folder_node(folder_id, (), subject_id)
        names[()] = materials[folder_id]['name'] if folder_id else subject_id
        if folder_id:
            weights[()] = materials[folder_id]['folder_weight']
    else:
        subjects = sorted({m['subject_id'] for m in materials.values()})
        collection = {subject: folder_node(None, (subject,), subject) for subject in subjects}
        for subject in subjects:
            names[(subject,)] = subject
    scheduler = FlashcardScheduler(collection, weights)
    for index, row in mapping.items():
        values = {field: row[field] for field in FIELDS}
        for field in ('due', 'last_review'):
            values[field] = datetime.fromisoformat(values[field]) if values[field] else None
        values['rating_counts'] = {rating: row[rating + '_count'] for rating in RATINGS}
        scheduler.cards[index] = Flashcard(question=row['question'], answer=row['answer'], **values)
    return scheduler, mapping, names, materials


def scope():
    return dict(subject_id=request.args.get('subject'), folder_id=request.args.get('folder'),
                deck_id=request.args.get('deck'))


def integer_limit(value, default):
    if value is None:
        return default
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise RequestError(400, 'Session limits must be non-negative whole numbers.') from None
    if str(number) != str(value) or number < 0:
        raise RequestError(400, 'Session limits must be non-negative whole numbers.')
    return number


@bp.get('/session')
def session():
    scheduler, mapping, _, materials = load_scheduler(**scope())
    now = datetime.now(timezone.utc)
    limit = integer_limit(request.args.get('limit'), 20)
    new_limit = integer_limit(request.args.get('newCardLimit'), 5)
    indices = scheduler.get_session(limit=limit, new_card_limit=new_limit, now=now)
    cards = []
    for index in indices:
        r = mapping[index]
        deck = materials[r['deck_id']]
        predictions = {}
        for rating in RATINGS:
            preview = FlashcardScheduler([])
            preview.cards[index] = deepcopy(scheduler.cards[index])
            due = preview.review(index, rating, now=now)
            predictions[rating] = {'due': due.isoformat(), 'seconds': (due-now).total_seconds()}
        cards.append({'id': r['id'], 'deckId': r['deck_id'], 'version': r['version'],
                      'question': r['question'], 'answer': r['answer'], 'demo': bool(r['demo']),
                      'fileId': deck['source_pdf_id'] or deck['id'], 'fileName': deck['name'],
                      'predictions': predictions})
    future = [c.due for c in scheduler.cards.values() if c.due > now]
    return jsonify(cards=cards, serverNow=now.isoformat(),
                   nextDue=min(future).isoformat() if future else None,
                   dueCount=sum(c.due <= now for c in scheduler.cards.values()))


@bp.post('/review')
def review():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise RequestError(400, 'Provide a review object.')
    deck_id, card_id = body.get('deckId'), body.get('cardId')
    if not isinstance(deck_id, str) or not isinstance(card_id, str) or type(body.get('version')) is not int:
        raise RequestError(400, 'Provide the deck, card and card version.')
    conn = db.get_db()
    # A write lock makes the version check, transition and history insertion atomic.
    conn.execute('BEGIN IMMEDIATE')
    try:
        scheduler, mapping, _, _ = load_scheduler(deck_id=deck_id)
        index = next((idx for idx, r in mapping.items() if r['id'] == card_id), None)
        if index is None:
            raise RequestError(409, 'This card changed or was removed. Refresh the session.')
        row = mapping[index]
        if row['version'] != body['version']:
            raise RequestError(409, 'This card was already reviewed or changed. Refresh the session.')
        now = datetime.now(timezone.utc)
        if scheduler.cards[index].due > now:
            raise RequestError(409, 'This card is not due yet. Refresh the session.')
        try:
            scheduler.review(index, body.get('rating'), now=now, response_seconds=body.get('responseSeconds'))
        except ValueError as exc:
            raise RequestError(400, str(exc)) from None
        card = scheduler.cards[index]
        values = []
        for field in FIELDS:
            value = getattr(card, field)
            values.append(value.isoformat() if isinstance(value, datetime) else value)
        columns = list(FIELDS) + [rating + '_count' for rating in RATINGS]
        values += [card.rating_counts[rating] for rating in RATINGS]
        values += [deck_id, card_id, current_user()['id'], body['version']]
        conn.execute('UPDATE flashcard_progress SET ' + ','.join(c+'=?' for c in columns) +
                     ',version=version+1 WHERE deck_id=? AND card_id=? AND user_id=? AND version=?', values)
        event = scheduler.review_log[-1]
        conn.execute('''INSERT INTO flashcard_reviews(user_id,deck_id,card_id,rating,reviewed_at,
                        response_seconds,card_version,next_due) VALUES(?,?,?,?,?,?,?,?)''',
                     (current_user()['id'], deck_id, card_id, event['rating'], now.isoformat(),
                      body.get('responseSeconds'), body['version'], card.due.isoformat()))
        conn.commit()
        return jsonify(due=card.due.isoformat(), version=body['version']+1, status=card.status)
    except Exception:
        conn.rollback()
        raise


@bp.get('/analytics')
def analytics():
    scheduler, _, names, _ = load_scheduler(**scope())
    data = scheduler.analytics()
    for item in data:
        path = tuple(item['path'])
        item['name'] = names.get(path, ' / '.join(map(str, path)))
        item['label'] = ' / '.join(names.get(path[:i], str(path[i-1])) for i in range(1, len(path)+1)) or names[()]
    return jsonify(data)
