""" Analytical Query Engine For MovieLens OLAP Dashboard, Answers the 7 project scenerios """


from django.db import connection


def get_movie_tags(movie_id, limit:int = 5):
    """Scenario 3.a: Top -5 tags based on the relevance score for a selected movie.
    Checks fact_genome_scores first; if empty, calculates normalized scores from fact_genome_tags."""

    with connection.cursor() as cur:
        cur.execute("""
            SELECT gt.tag, ROUND(gs.relevance::numeric, 4) AS
            relevance
            FROM fact_genome_scores gs
            JOIN dim_genome_tags gt ON gs.tag_id = gt.tag_id
            WHERE gs.movie_id = %s
            ORDER BY gs.relevance DESC
            LIMIT %s
        """, [movie_id, limit])
        rows = cur.fetchall()

        if rows:
            return [{'tag': r[0], 'relevance': float(r[1])} for r in rows]

        # Fallback to normalized tag frequency from fact_tags
        cur.execute("""
            SELECT
                tag,
                COUNT(*) AS tag_count,
                ROUND(COUNT(*)::numeric /
                SUM(COUNT(*)) OVER (), 4) AS relevance
            FROM fact_tags
            WHERE movie_id = %s
            GROUP BY tag
            ORDER BY tag_count DESC
            LIMIT %s;
        """, [movie_id, limit])
        rows = cur.fetchall()
        return [{'tag': r[0], 'relevance': float(r[2]), 'count': r[1]} for r in rows]

def get_top_movies(year: int = None, min_ratings: int
            = 100, limit: int = 10):
    """
    Scenario 3(b): Overall and year-wise top 10
    movies based on average rating.
    Uses mv_movie_rating_stats for instant execution.
    """
    with connection.cursor() as cur:
        if year:
            cur.execute("""
                SELECT movie_id, title, release_year,
                avg_rating, total_ratings
                FROM mv_movie_rating_stats
                WHERE release_year = %s AND
                    total_ratings >= %s
                    ORDER BY avg_rating DESC,
                    total_ratings DESC
                    LIMIT %s;
                """, [year, min_ratings, limit])
        else:
            cur.execute("""
                SELECT movie_id, title, release_year,
                avg_rating, total_ratings
                FROM mv_movie_rating_stats
                WHERE total_ratings >= %s
                ORDER BY avg_rating DESC,
                total_ratings DESC
                LIMIT %s;
                """, [min_ratings, limit])
        rows = cur.fetchall()
        return [{
            'movie_id': r[0],
            'title': r[1],
            'release_year': r[2],
            'avg_rating': float(r[3]),
            'total_ratings': r[4]
        } for r in rows]

def get_popular_tags_by_genre(limit_per_genre: int = 5):
    """
    Scenario 3(c): Most popular tags given for each genre.
    Uses precomputed mv_popular_tags_genre for sub-millisecond execution.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT genre_name, tag, tag_count
            FROM mv_popular_tags_genre
            WHERE rnk <= %s
            ORDER BY genre_name, rnk;
        """, [limit_per_genre])
        rows = cur.fetchall()
        result = {}
        for genre, tag, count in rows:
            result.setdefault(genre, []).append({'tag': tag, 'count': count})
        return result


def get_movie_rating_distribution(movie_id: int):
    """
    Scenario 3(d): Distribution of users' ratings
    (0.5 to 5.0) for a selected movie.
    Uses index-only scan on
    idx_fact_ratings_movie_rating (sub-15ms on 32M
    rows).
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT rating, COUNT(*) AS rating_count
            FROM fact_ratings
            WHERE movie_id = %s
            GROUP BY rating
            ORDER BY rating ASC;
        """, [movie_id])
        rows = cur.fetchall()

        # Ensure all intervals from 0.5 to 5.0 are
        # represented
        all_ratings = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0,
            3.5, 4.0, 4.5, 5.0]
        data_map = {float(r[0]): r[1] for r in rows}
        return [{'rating': r, 'count':
            data_map.get(r, 0)} for r in all_ratings]


def get_total_ratings_distribution():
    """
    Scenario 3(e): Overall distribution of total
    ratings across movies (power-law buckets).
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                CASE
                    WHEN total_ratings = 1 THEN '1 rating'
                    WHEN total_ratings BETWEEN 2 AND
                        10 THEN '2-10'
                    WHEN total_ratings BETWEEN 11 AND
                        50 THEN '11-50'
                    WHEN total_ratings BETWEEN 51 AND
                        200 THEN '51-200'
                    WHEN total_ratings BETWEEN 201
                        AND 1000 THEN '201-1,000'
                    WHEN total_ratings BETWEEN 1001
                        AND 5000 THEN '1,001-5,000'
                    ELSE '5,000+ ratings'
                END AS bucket_label,
                CASE
                    WHEN total_ratings = 1 THEN 1
                    WHEN total_ratings BETWEEN 2 AND
                        10 THEN 2
                    WHEN total_ratings BETWEEN 11 AND
                        50 THEN 3
                    WHEN total_ratings BETWEEN 51 AND
                        200 THEN 4
                    WHEN total_ratings BETWEEN 201
                        AND 1000 THEN 5
                    WHEN total_ratings BETWEEN 1001
                        AND 5000 THEN 6
                    ELSE 7
                END AS sort_order,
                COUNT(*) AS movie_count
            FROM mv_movie_rating_stats
            GROUP BY bucket_label, sort_order
            ORDER BY sort_order;
        """)
        rows = cur.fetchall()
        return [{'bucket': r[0], 'count': r[2]} for r
        in rows]


def get_dominant_genre(year: int):
    """
    Scenario 3(f): For a particular year, show which
    genre released the highest number of movies.
    Returns dominant genre plus all genres for that
    year for charting.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT genre_name, movie_count
            FROM mv_genre_year_summary
            WHERE release_year = %s
            ORDER BY movie_count DESC;
        """, [year])
        rows = cur.fetchall()

        if not rows:
            return {'year': year, 'dominant': None,
            'all_genres': []}
        return {
            'year': year,
            'dominant': {'genre': rows[0][0],
            'count': rows[0][1]},
            'all_genres': [{'genre': r[0], 'count':
            r[1]} for r in rows]
        }


def get_genre_coverage():
    """
    Scenario 3(g): Show genre-wise coverage of
    movies.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                g.genre_name,
                COUNT(b.movie_id) AS movie_count,
                ROUND(COUNT(b.movie_id) * 100.0 /
                (SELECT COUNT(*) FROM dim_movies), 2)
                AS coverage_pct
            FROM dim_genres g
            JOIN bridge_movie_genre b ON g.genre_id =
            b.genre_id
            GROUP BY g.genre_id, g.genre_name
            ORDER BY movie_count DESC;
        """)
        rows = cur.fetchall()
        return [{
            'genre': r[0],
            'movie_count': r[1],
            'coverage_pct': float(r[2])
        } for r in rows]


def search_movies(query_str: str, limit: int = 10):
    """
    Helper for Autocomplete Search: Lookup movies by
    title.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT movie_id, title, release_year
            FROM dim_movies
            WHERE title ILIKE %s
            ORDER BY release_year DESC NULLS LAST,
            movie_id ASC
            LIMIT %s;
        """, [f"%{query_str}%", limit])
        rows = cur.fetchall()
        return [{'movie_id': r[0], 'title': r[1],
            'release_year': r[2]} for r in rows]


def get_movie_details(movie_id: int):
    """
    Returns full metadata for a movie: title, year, avg_rating, total_ratings, and genres.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                m.movie_id,
                m.title,
                m.release_year,
                COALESCE(s.avg_rating, 0) AS avg_rating,
                COALESCE(s.total_ratings, 0) AS total_ratings,
                COALESCE(ARRAY_AGG(g.genre_name ORDER BY g.genre_name) FILTER (WHERE g.genre_name IS NOT NULL), '{}') AS genres
            FROM dim_movies m
            LEFT JOIN mv_movie_rating_stats s ON m.movie_id = s.movie_id
            LEFT JOIN bridge_movie_genre b ON m.movie_id = b.movie_id
            LEFT JOIN dim_genres g ON b.genre_id = g.genre_id
            WHERE m.movie_id = %s
            GROUP BY m.movie_id, m.title, m.release_year, s.avg_rating, s.total_ratings;
        """, [movie_id])
        row = cur.fetchone()
        if not row:
            return None
        return {
            'movie_id': row[0],
            'title': row[1],
            'release_year': row[2],
            'avg_rating': float(row[3]),
            'total_ratings': row[4],
            'genres': row[5]
        }


def upsert_user_rating(user_id: int, movie_id: int, rating: float):
    """
    Problem 4: Allows a user to rate or modify an existing rating.
    """
    import datetime
    today = datetime.date.today()
    date_key = today.year * 10000 + today.month * 100 + today.day

    with connection.cursor() as cur:
        # 1. Ensure date_key exists in dim_date
        cur.execute("""
            INSERT INTO dim_date (date_key, full_date, year, quarter, month, day)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (date_key) DO NOTHING;
        """, [date_key, today, today.year, (today.month - 1) // 3 + 1, today.month, today.day])

        # 2. Ensure user exists in dim_users
        cur.execute("""
            INSERT INTO dim_users (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING;
        """, [user_id])

        # 3. Check for existing rating by user for this movie
        cur.execute("""
            SELECT rating_id FROM fact_ratings
            WHERE user_id = %s AND movie_id = %s;
        """, [user_id, movie_id])
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE fact_ratings
                SET rating = %s, date_key = %s
                WHERE rating_id = %s;
            """, [rating, date_key, existing[0]])
            action = 'updated'
        else:
            cur.execute("""
                INSERT INTO fact_ratings (user_id, movie_id, date_key, rating)
                VALUES (%s, %s, %s, %s);
            """, [user_id, movie_id, date_key, rating])
            action = 'inserted'

        return {
            'action': action,
            'user_id': user_id,
            'movie_id': movie_id,
            'rating': rating,
            'date_key': date_key
        }

