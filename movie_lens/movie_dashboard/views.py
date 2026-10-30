import json
import time
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from .services import analytics


def dashboard_view(request):
    """Renders the executive OLAP analytics dashboard."""
    return render(request, 'dashboard.html')


# -------------------------------------------------------------
# 1. Movie Search & Details Endpoints
# -------------------------------------------------------------

def api_search_movies(request):
    """Autocomplete search endpoint matching movies by title prefix/substring."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'results': []})
    limit = int(request.GET.get('limit', 10))
    results = analytics.search_movies(query, limit=limit)
    return JsonResponse({'results': results})


def api_movie_details(request):
    """Fetches high-level metadata, genre tags, and stats for a single movie."""
    movie_id = request.GET.get('movie_id')
    if not movie_id:
        return JsonResponse({'error': 'movie_id is required'}, status=400)
    try:
        movie_id = int(movie_id)
    except ValueError:
        return JsonResponse({'error': 'Invalid movie_id format'}, status=400)

    details = analytics.get_movie_details(movie_id)
    if not details:
        return JsonResponse({'error': 'Movie not found'}, status=404)
    return JsonResponse(details)


# -------------------------------------------------------------
# 2. Scenario 3(a): Top-5 Tag Relevance per Movie
# -------------------------------------------------------------

def api_movie_tags(request):
    """
    Scenario 3(a): For a particular movie, show the top-5 tags
    based on the relevance scores of the tags for that movie.
    """
    t0 = time.time()
    movie_id = request.GET.get('movie_id', 1)
    limit = int(request.GET.get('limit', 5))
    try:
        movie_id = int(movie_id)
    except ValueError:
        return JsonResponse({'error': 'Invalid movie_id'}, status=400)

    tags = analytics.get_movie_tags(movie_id, limit=limit)
    latency_ms = round((time.time() - t0) * 1000, 2)
    return JsonResponse({'movie_id': movie_id, 'tags': tags, 'latency_ms': latency_ms})


# -------------------------------------------------------------
# 3. Scenario 3(b): Overall & Year-wise Top 10 Movies
# -------------------------------------------------------------

def api_top_movies(request):
    """
    Scenario 3(b): Show overall and year-wise top 10 movies
    based on average rating (min 100 ratings threshold by default).
    """
    t0 = time.time()
    year = request.GET.get('year')
    limit = int(request.GET.get('limit', 10))
    min_ratings = int(request.GET.get('min_ratings', 100))

    year_int = int(year) if year and year.isdigit() else None
    movies = analytics.get_top_movies(year=year_int, min_ratings=min_ratings, limit=limit)
    latency_ms = round((time.time() - t0) * 1000, 2)
    return JsonResponse({'year': year_int, 'movies': movies, 'latency_ms': latency_ms})


# -------------------------------------------------------------
# 4. Scenario 3(c): Most Popular Tags by Genre
# -------------------------------------------------------------

def api_popular_tags_genre(request):
    """
    Scenario 3(c): What are the most popular tags given for each genre.
    """
    t0 = time.time()
    limit = int(request.GET.get('limit', 5))
    genres = analytics.get_popular_tags_by_genre(limit_per_genre=limit)
    latency_ms = round((time.time() - t0) * 1000, 2)
    return JsonResponse({'genres': genres, 'latency_ms': latency_ms})


# -------------------------------------------------------------
# 5. Scenario 3(d): Rating Distribution for a Particular Movie
# -------------------------------------------------------------

def api_movie_rating_distribution(request):
    """
    Scenario 3(d): For a particular movie, show the distribution
    of users' ratings (0.5 to 5.0).
    """
    t0 = time.time()
    movie_id = request.GET.get('movie_id', 1)
    try:
        movie_id = int(movie_id)
    except ValueError:
        return JsonResponse({'error': 'Invalid movie_id'}, status=400)

    dist = analytics.get_movie_rating_distribution(movie_id)
    latency_ms = round((time.time() - t0) * 1000, 2)
    return JsonResponse({'movie_id': movie_id, 'distribution': dist, 'latency_ms': latency_ms})


# -------------------------------------------------------------
# 6. Scenario 3(e): Distribution of Total Ratings Across Movies
# -------------------------------------------------------------

def api_total_ratings_distribution(request):
    """
    Scenario 3(e): Show the distribution of total ratings for movies (power law).
    """
    t0 = time.time()
    dist = analytics.get_total_ratings_distribution()
    latency_ms = round((time.time() - t0) * 1000, 2)
    return JsonResponse({'distribution': dist, 'latency_ms': latency_ms})


# -------------------------------------------------------------
# 7. Scenario 3(f): Dominant Genre for a Given Year
# -------------------------------------------------------------

def api_dominant_genre(request):
    """
    Scenario 3(f): For a particular year, show which genre released the highest number of movies.
    """
    t0 = time.time()
    year = request.GET.get('year', 2017)
    try:
        year = int(year)
    except ValueError:
        return JsonResponse({'error': 'Invalid year format'}, status=400)

    data = analytics.get_dominant_genre(year)
    latency_ms = round((time.time() - t0) * 1000, 2)
    data['latency_ms'] = latency_ms
    return JsonResponse(data)


# -------------------------------------------------------------
# 8. Scenario 3(g): Genre-wise Movie Coverage
# -------------------------------------------------------------

def api_genre_coverage(request):
    """
    Scenario 3(g): Show genre-wise coverage of movies across entire catalog.
    """
    t0 = time.time()
    coverage = analytics.get_genre_coverage()
    latency_ms = round((time.time() - t0) * 1000, 2)
    return JsonResponse({'coverage': coverage, 'latency_ms': latency_ms})


# -------------------------------------------------------------
# 9. Problem 4: Role-Based User Interaction - Rate Movie
# -------------------------------------------------------------

@csrf_exempt
def api_submit_rating(request):
    """
    Problem 4: Users are allowed to modify only the rating of movies.
    Accepts JSON: { "movie_id": <int>, "rating": <float 0.5-5.0> }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
        movie_id = int(data.get('movie_id'))
        rating = float(data.get('rating'))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    if rating < 0.5 or rating > 5.0 or (round(rating * 2) != rating * 2):
        return JsonResponse({'error': 'Rating must be between 0.5 and 5.0 in 0.5 increments'}, status=400)

    user_id = request.user.id if request.user.is_authenticated else 1
    result = analytics.upsert_user_rating(user_id=user_id, movie_id=movie_id, rating=rating)
    return JsonResponse({
        'success': True,
        'action': result['action'],
        'movie_id': movie_id,
        'rating': rating,
        'user_id': user_id,
        'message': f"Rating successfully {result['action']} to {rating}★"
    })
