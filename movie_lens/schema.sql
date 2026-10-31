    -- 1. Dim Movies
CREATE TABLE IF NOT EXISTS dim_movies (
    movie_id INT PRIMARY KEY,
    title TEXT NOT NULL,
    release_year INT
    );

    -- 2. Dim Genres
    CREATE TABLE IF NOT EXISTS dim_genres (
        genre_id INT PRIMARY KEY,
        genre_name VARCHAR(100) NOT NULL UNIQUE
    );

    -- 3. Bridge Movie-Genre (Resolves M:Nrelationship, Composite PK)
    CREATE TABLE IF NOT EXISTS
    bridge_movie_genre (
        movie_id INT NOT NULL REFERENCES
        dim_movies(movie_id) ON DELETE CASCADE,
        genre_id INT NOT NULL REFERENCES
        dim_genres(genre_id) ON DELETE CASCADE,
        PRIMARY KEY (movie_id, genre_id)
    );

    -- 4. Dim Users
    CREATE TABLE IF NOT EXISTS dim_users (
        user_id INT PRIMARY KEY
    );

    -- 5. Dim Date (Temporal Dimension)
    CREATE TABLE IF NOT EXISTS dim_date (
        date_key INT PRIMARY KEY,
        full_date DATE NOT NULL,
        year INT NOT NULL,
        quarter INT NOT NULL,
        month INT NOT NULL,
        day INT NOT NULL
    );

    -- 6. Fact Ratings (Grain: One rating per user per movie)
    CREATE TABLE IF NOT EXISTS fact_ratings (
        rating_id BIGSERIAL PRIMARY KEY,
  	user_id INT NOT NULL REFERENCES
        dim_users(user_id),
        movie_id INT NOT NULL REFERENCES
        dim_movies(movie_id),
        date_key INT NOT NULL REFERENCES
  	dim_date(date_key),
        rating NUMERIC(2, 1) NOT NULL CHECK
        (rating >= 0.5 AND rating <= 5.0)
    );

    -- 7. Fact Tags (Grain: One tag assignmentper user per movie)
    CREATE TABLE IF NOT EXISTS fact_tags (
        tag_id BIGSERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES
        dim_users(user_id),
        movie_id INT NOT NULL REFERENCES
        dim_movies(movie_id),
        date_key INT NOT NULL REFERENCES
        dim_date(date_key),
        tag TEXT NOT NULL
    );

    -- 8. Dim Genome Tags (Question 3a)
    CREATE TABLE IF NOT EXISTS dim_genome_tags (
        tag_id INT PRIMARY KEY,
        tag TEXT NOT NULL
    );

    -- 9. Fact Genome Scores (Question 3a)
	CREATE TABLE	IF NOT EXISTS
    fact_genome_scores (
        movie_id INT NOT NULL REFERENCES
        dim_movies(movie_id),
        tag_id INT NOT NULL REFERENCES
        dim_genome_tags(tag_id),
        relevance DOUBLE PRECISION NOT NULL,
  	PRIMARY KEY (movie_id, tag_id)
    );
