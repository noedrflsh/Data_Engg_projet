from django.urls import path
from . import views

urlpatterns = [
    # Dashboard View
    path('', views.dashboard_view, name='dashboard'),

    # Autocomplete & Details
    path('api/movies/search/', views.api_search_movies, name='api_search_movies'),
    path('api/movies/details/', views.api_movie_details, name='api_movie_details'),

    # 7 Analytical OLAP Endpoints
    path('api/analytics/movie-tags/', views.api_movie_tags, name='api_movie_tags'),
    path('api/analytics/top-movies/', views.api_top_movies, name='api_top_movies'),
    path('api/analytics/popular-tags-genre/', views.api_popular_tags_genre, name='api_popular_tags_genre'),
    path('api/analytics/rating-distribution/', views.api_movie_rating_distribution, name='api_movie_rating_distribution'),
    path('api/analytics/total-ratings-distribution/', views.api_total_ratings_distribution, name='api_total_ratings_distribution'),
    path('api/analytics/dominant-genre/', views.api_dominant_genre, name='api_dominant_genre'),
    path('api/analytics/genre-coverage/', views.api_genre_coverage, name='api_genre_coverage'),

    # Problem 4: User Rating Interaction
    path('api/ratings/rate/', views.api_submit_rating, name='api_submit_rating'),
]
