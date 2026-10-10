"""The app's HTTP surface: who the caller is, and what they get without a proxy."""
import tempfile
import unittest

from tests.support import build_app


class AuthTests(unittest.TestCase):
    def test_health_needs_no_user(self):
        with tempfile.TemporaryDirectory() as temp:
            response = build_app(temp).test_client().get('/api/health')
            self.assertEqual((response.status_code, response.get_json()), (200, {'ok': True}))

    def test_api_without_the_proxy_header_is_unauthorized(self):
        with tempfile.TemporaryDirectory() as temp:
            client = build_app(temp).test_client()
            for path in ('/api/me', '/api/dashboard', '/api/learning/health'):
                response = client.get(path)
                self.assertEqual((path, response.status_code, response.get_json()),
                                 (path, 401, {'error': 'unauthorized'}))

    def test_a_malformed_user_header_is_unauthorized(self):
        with tempfile.TemporaryDirectory() as temp:
            client = build_app(temp).test_client()
            for value in ('', 'not-an-email', 'two words@ethz.ch', 'a@b.ch ' + 'x' * 250):
                self.assertEqual(client.get('/api/me', headers={'X-User-Id': value}).status_code, 401, value)

    def test_the_proxy_headers_identify_and_create_the_user(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp)
            client = app.test_client()
            response = client.get('/api/me', headers={'X-User-Id': 'new.person@ethz.ch',
                                                      'X-User-Name': 'Ren%C3%A9%20M%C3%BCller'})
            self.assertEqual(response.get_json(), {'email': 'new.person@ethz.ch', 'name': 'René Müller'})
            # A later request with a new display name updates the row rather than adding one.
            client.get('/api/me', headers={'X-User-Id': 'NEW.PERSON@ethz.ch', 'X-User-Name': 'Ren%C3%A9%20M.'})
            with app.app_context():
                import db
                rows = db.get_db().execute('SELECT email, display_name FROM users').fetchall()
            self.assertEqual([tuple(r) for r in rows], [('new.person@ethz.ch', 'René M.')])

    def test_a_missing_name_header_falls_back_to_the_local_part(self):
        with tempfile.TemporaryDirectory() as temp:
            response = build_app(temp).test_client().get('/api/me', headers={'X-User-Id': 'hans@ethz.ch'})
            self.assertEqual(response.get_json()['name'], 'hans')

    def test_dev_user_stands_in_for_the_proxy_and_a_header_still_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            client = build_app(temp, DEV_USER='alice@ethz.ch', DEV_USER_NAME='Alice Example').test_client()
            self.assertEqual(client.get('/api/me').get_json(),
                             {'email': 'alice@ethz.ch', 'name': 'Alice Example'})
            self.assertEqual(client.get('/api/me', headers={'X-User-Id': 'bob@ethz.ch'}).get_json()['email'],
                             'bob@ethz.ch')

    def test_sign_out_is_offered_only_to_a_request_from_the_proxy(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, DEV_USER='alice@ethz.ch', SIGN_OUT_URL='https://auth.example/logout')
            client = app.test_client()
            self.assertNotIn('signOutUrl', client.get('/api/me').get_json())
            through_proxy = client.get('/api/me', headers={'X-User-Id': 'alice@ethz.ch'}).get_json()
            self.assertEqual(through_proxy['signOutUrl'], 'https://auth.example/logout')
            # Configuring it empty hides the button everywhere.
            silent = build_app(temp, SIGN_OUT_URL='').test_client()
            self.assertNotIn('signOutUrl', silent.get('/api/me', headers={'X-User-Id': 'a@ethz.ch'}).get_json())

    def test_a_seeded_user_keeps_their_data(self):
        with tempfile.TemporaryDirectory() as temp:
            client = build_app(temp, seed=True).test_client()
            data = client.get('/api/dashboard', headers={'X-User-Id': 'alice@ethz.ch'}).get_json()
            self.assertEqual(data['user']['email'], 'alice@ethz.ch')
            self.assertEqual([s['label'] for s in data['semesters']], ['HS25', 'FS26'])
            # A visitor the seed does not know gets an account, not someone else's data.
            fresh = client.get('/api/dashboard', headers={'X-User-Id': 'guest@ethz.ch'}).get_json()
            self.assertEqual(fresh['semesters'], [])


if __name__ == '__main__':
    unittest.main()
