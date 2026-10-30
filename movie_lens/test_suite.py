"""
Comprehensive Test & Verification Suite for MovieLens OLAP Dashboard
Runs directly against the populated PostgreSQL database.
"""
import os
import sys
import time
import json
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_lens_dashboard.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth.models import User


class MovieLensIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = Client()
        # Ensure demo_user exists for authenticated tests
        if not User.objects.filter(username='demo_user').exists():
            User.objects.create_user(username='demo_user', password='movielens2024', is_staff=False)

    def test_01_dashboard_root(self):
        """Verify HTML dashboard loads successfully."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'MovieLens Analytics', res.content)

    def test_02_movie_details(self):
        """Verify movie details endpoint."""
        res = self.client.get('/api/movies/details/?movie_id=1')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data['movie_id'], 1)
        self.assertEqual(data['title'], 'Toy Story')
        self.assertEqual(data['release_year'], 1995)
        self.assertIn('Animation', data['genres'])

    def test_03_search_autocomplete(self):
        """Verify autocomplete search matches titles."""
        res = self.client.get('/api/movies/search/?q=inception')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertIn('results', data)
        self.assertGreater(len(data['results']), 0)
        self.assertEqual(data['results'][0]['title'], 'Inception')

    def test_04_scenario_3a_movie_tags(self):
        """Scenario 3(a): Top-5 tag relevance for movie."""
        res = self.client.get('/api/analytics/movie-tags/?movie_id=1&limit=5')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data['movie_id'], 1)
        self.assertLessEqual(len(data['tags']), 5)
        self.assertTrue(all('tag' in t and 'relevance' in t for t in data['tags']))

    def test_05_scenario_3b_top_movies_overall(self):
        """Scenario 3(b): Overall top 10 movies."""
        res = self.client.get('/api/analytics/top-movies/?limit=10')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertLessEqual(len(data['movies']), 10)
        self.assertTrue(all(m['avg_rating'] >= 4.0 for m in data['movies']))

    def test_06_scenario_3b_top_movies_year(self):
        """Scenario 3(b): Year-wise top 10 movies (2017)."""
        res = self.client.get('/api/analytics/top-movies/?year=2017&limit=5')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data['year'], 2017)
        self.assertLessEqual(len(data['movies']), 5)

    def test_07_scenario_3c_popular_tags_genre(self):
        """Scenario 3(c): Popular tags by genre."""
        res = self.client.get('/api/analytics/popular-tags-genre/?limit=3')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertIn('genres', data)
        self.assertIn('Action', data['genres'])
        self.assertIn('Drama', data['genres'])

    def test_08_scenario_3d_rating_distribution(self):
        """Scenario 3(d): Rating distribution for movie."""
        res = self.client.get('/api/analytics/rating-distribution/?movie_id=1')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data['movie_id'], 1)
        self.assertEqual(len(data['distribution']), 10) # 0.5 to 5.0

    def test_09_scenario_3e_ratings_volume_distribution(self):
        """Scenario 3(e): Total ratings volume distribution (power law)."""
        res = self.client.get('/api/analytics/total-ratings-distribution/')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertIn('distribution', data)
        self.assertGreater(len(data['distribution']), 0)

    def test_10_scenario_3f_dominant_genre(self):
        """Scenario 3(f): Dominant genre for specified year."""
        res = self.client.get('/api/analytics/dominant-genre/?year=2017')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data['year'], 2017)
        self.assertEqual(data['dominant']['genre'], 'Drama')

    def test_11_scenario_3g_genre_coverage(self):
        """Scenario 3(g): Genre-wise movie coverage."""
        res = self.client.get('/api/analytics/genre-coverage/')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertIn('coverage', data)
        self.assertGreater(len(data['coverage']), 0)

    def test_12_problem_4_rating_submission(self):
        """Problem 4: Rate movie / modify existing rating with auth enforcement."""
        payload = {'movie_id': 1, 'rating': 4.5}

        # 1. Unauthenticated request should be rejected (HTTP 401)
        self.client.logout()
        res = self.client.post('/api/ratings/rate/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 401)
        data = json.loads(res.content)
        self.assertIn('error', data)

        # 2. Authenticated user can rate/modify
        logged_in = self.client.login(username='demo_user', password='movielens2024')
        self.assertTrue(logged_in)

        res = self.client.post('/api/ratings/rate/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['rating'], 4.5)
        self.assertEqual(data['username'], 'demo_user')

    def test_13_authentication_endpoints(self):
        """Verify login, register, and current user info endpoints."""
        self.client.logout()

        # Test login page GET for guest
        res = self.client.get('/login/')
        self.assertEqual(res.status_code, 200)

        # Test register page GET for guest
        res = self.client.get('/register/')
        self.assertEqual(res.status_code, 200)

        # Test current user endpoint
        self.client.login(username='demo_user', password='movielens2024')
        res = self.client.get('/api/user/me/')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['authenticated'])
        self.assertEqual(data['username'], 'demo_user')
        self.assertEqual(data['role'], 'User')


if __name__ == '__main__':
    print('======================================================================')
    print(' Running MovieLens OLAP End-to-End Integration Test Suite')
    print('======================================================================')
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(MovieLensIntegrationTests)
    result = runner.run(suite)
    if result.wasSuccessful():
        print('\n All 13 integration tests passed with 100% success!')
        sys.exit(0)
    else:
        print('\n Tests encountered failures.')
        sys.exit(1)
