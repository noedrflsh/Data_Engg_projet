-- ==============================================================
-- MovieLens OLAP Performance Indexing & Materialized Views
-- ==============================================================

-- 1. Covering index for movie rating aggregations & distributions (Questions 3b & 3d)
CREATE INDEX IF NOT EXISTS idx_fact_ratings_movie_rating
ON fact_ratings (movie_id, rating);

-- 1b. Fast index for user rating lookups & upserts (Problem 4)
CREATE INDEX IF NOT EXISTS idx_fact_ratings_user_movie
ON fact_ratings (user_id, movie_id);

-- 2. Index for date-based queries
CREATE INDEX IF NOT EXISTS idx_fact_ratings_date_key
ON fact_ratings (date_key);

-- 3. Release year lookups (Questions 3b & 3f)
CREATE INDEX IF NOT EXISTS idx_dim_movies_release_year
ON dim_movies (release_year);

-- 4. Reverse lookup for genres (Questions 3c & 3g)
CREATE INDEX IF NOT EXISTS idx_bridge_movie_genre_genre
ON bridge_movie_genre (genre_id, movie_id);

-- 5. Fact tags lookups
CREATE INDEX IF NOT EXISTS idx_fact_tags_movie ON fact_tags (movie_id);
CREATE INDEX IF NOT EXISTS idx_fact_tags_tag ON fact_tags (tag);

-- 6. Genome scores lookups (Question 3a: Top-5 Tag Relevance)
CREATE INDEX IF NOT EXISTS idx_fact_genome_scores_movie_rel
ON fact_genome_scores (movie_id, relevance DESC);

-- 7. Materialized View: Movie Rating Summaries (Questions 3b & 3d base)
-- Precomputes average rating and vote count per movie
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_movie_rating_stats AS
SELECT
    m.movie_id,
    m.title,
    m.release_year,
    COUNT(r.rating) AS total_ratings,
    ROUND(AVG(r.rating)::numeric, 2) AS avg_rating
FROM dim_movies m
JOIN fact_ratings r ON m.movie_id = r.movie_id
GROUP BY m.movie_id, m.title, m.release_year;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_movie_id ON mv_movie_rating_stats(movie_id);
CREATE INDEX IF NOT EXISTS idx_mv_rating_year ON mv_movie_rating_stats(release_year, avg_rating DESC);

-- 8. Materialized View: Genre Year Summary (Questions 3f & 3g)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_genre_year_summary AS
SELECT
    g.genre_id,
    g.genre_name,
    m.release_year,
    COUNT(m.movie_id) AS movie_count
FROM dim_genres g
JOIN bridge_movie_genre b ON g.genre_id = b.genre_id
JOIN dim_movies m ON b.movie_id = m.movie_id
WHERE m.release_year IS NOT NULL
GROUP BY g.genre_id, g.genre_name, m.release_year;

CREATE INDEX IF NOT EXISTS idx_mv_gy ON mv_genre_year_summary(release_year, movie_count DESC);

-- 9. Materialized View: Most Popular Tags by Genre (Question 3c)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_popular_tags_genre AS
WITH ranked_tags AS (
    SELECT
        g.genre_name,
        t.tag,
        COUNT(*) AS tag_count,
        ROW_NUMBER() OVER (PARTITION BY g.genre_name ORDER BY COUNT(*) DESC) AS rnk
    FROM dim_genres g
    JOIN bridge_movie_genre b ON g.genre_id = b.genre_id
    JOIN fact_tags t ON b.movie_id = t.movie_id
    GROUP BY g.genre_name, t.tag
)
SELECT genre_name, tag, tag_count, rnk
FROM ranked_tags
WHERE rnk <= 15;

CREATE INDEX IF NOT EXISTS idx_mv_popular_tags_genre_rnk ON mv_popular_tags_genre(genre_name, rnk);

-- 10. Grant privileges to Django application user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gumbo;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO gumbo;
GRANT ALL PRIVILEGES ON TABLE mv_movie_rating_stats, mv_genre_year_summary, mv_popular_tags_genre TO gumbo;
