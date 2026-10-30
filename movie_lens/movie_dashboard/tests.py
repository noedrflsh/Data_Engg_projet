from django.test import TestCase, Client
import json


class MovieLensAnalyticsAPITests(TestCase):
    """
    Automated test suite verifying all 7 analytical scenarios,
    movie search autocomplete, metadata details, and user rating submission.
    """

    def setUp(self):
        self.client = Client()

    def test_dashboard_renders(self):
        """Verify dashboard root HTML page loads successfully."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MovieLens Analytics')

    def test_movie_details_api(self):
        """Verify movie details endpoint returns metadata and genre list."""
        response = self.client.get('/api/movies/details/?movie_id=1')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['movie_id'], 1)
        self.assertIn('Toy Story', data['title'])
        self.assertIsInstance(data['genres'], list)

    def test_search_autocomplete_api(self):
        """Verify search autocomplete matches movie titles."""
        response = self.client.get('/api/movies/search/?q=toy')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)
        self.assertGreater(len(data['results']), 0)

    def test_scenario_3a_movie_tags(self):
        """Scenario 3(a): Top-5 tags by relevance for a movie."""
        response = self.client.get('/api/analytics/movie-tags/?movie_id=1&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['movie_id'], 1)
        self.assertIn('tags', data)
        self.assertLessEqual(len(data['tags']), 5)

    def test_scenario_3b_top_movies(self):
        """Scenario 3(b): Overall and year-wise top 10 movies."""
        # Overall
        res_overall = self.client.get('/api/analytics/top-movies/?limit=10')
        self.assertEqual(res_overall.status_code, 200)
        data_overall = json.loads(res_overall.content)
        self.assertLessEqual(len(data_overall['movies']), 10)

        # Year-wise
        res_year = self.client.get('/api/analytics/top-movies/?year=2017&limit=5')
        self.assertEqual(res_year.status_code, 200)
        data_year = json.loads(res_year.content)
        self.assertEqual(data_year['year'], 2017)

    def test_scenario_3c_popular_tags_genre(self):
        """Scenario 3(c): Most popular tags given for each genre."""
        response = self.client.get('/api/analytics/popular-tags-genre/?limit=3')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('genres', data)
        self.assertIn('Action', data['genres'])

    def test_scenario_3d_rating_distribution(self):
        """Scenario 3(d): Rating distribution (0.5 to 5.0) for a selected movie."""
        response = self.client.get('/api/analytics/rating-distribution/?movie_id=1')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['movie_id'], 1)
        self.assertEqual(len(data['distribution']), 10) # 0.5, 1.0, ..., 5.0

    def test_scenario_3e_total_ratings_distribution(self):
        """Scenario 3(e): Overall distribution of total ratings across movies."""
        response = self.client.get('/api/analytics/total-ratings-distribution/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('distribution', data)
        self.assertGreater(len(data['distribution']), 0)

    def test_scenario_3f_dominant_genre(self):
        """Scenario 3(f): Dominant genre for a specified year."""
        response = self.client.get('/api/analytics/dominant-genre/?year=2017')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['year'], 2017)
        self.assertIn('dominant', data)
        self.assertEqual(data['dominant']['genre'], 'Drama')

    def test_scenario_3g_genre_coverage(self):
        """Scenario 3(g): Genre-wise coverage of movies."""
        response = self.client.get('/api/analytics/genre-coverage/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('coverage', data)
        self.assertGreater(len(data['coverage']), 0)

    def test_problem_4_rating_submission(self):
        """Problem 4: User interactive rating submission and modification."""
        payload = {'movie_id': 1, 'rating': 4.5}
        response = self.client.post(
            '/api/ratings/rate/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['rating'], 4.5)
