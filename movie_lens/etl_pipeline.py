import io
import time
import os
import re
import pandas as pd
import numpy as np
import psycopg

DB_URI = "dbname=movie_lens user=gumbo password=2836 host=localhost port=5432"

def fast_copy(cur, table_name, columns, buffer):
    buffer.seek(0)
    col_str = ", ".join(columns)
    sql = f"COPY {table_name} ({col_str}) FROM STDIN WITH (FORMAT text)"
    with cur.copy(sql) as copy:
        copy.write(buffer.getvalue())

def run_etl():
    print("==================================================")
    print("      MovieLens OLAP High-Speed Ingestion         ")
    print("==================================================")
    start_total = time.time()
    
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            # Check existing counts to skip already loaded tables
            cur.execute("SELECT count(*) FROM dim_movies;")
            movies_count = cur.fetchone()[0]
            
            cur.execute("SELECT count(*) FROM fact_ratings;")
            ratings_count = cur.fetchone()[0]

            # ---------------------------------------------------------
            # 1. Dim Movies, Dim Genres & Bridge Table
            # ---------------------------------------------------------
            if movies_count > 0:
                print(f"\n[Step 1/5] dim_movies already has {movies_count:,} rows. Skipping...")
            else:
                print("\n[Step 1/5] Ingesting Dim Movies, Genres & Bridge (1NF Normalization)...")
                movies_csv_path = 'ml-32m/movies.csv'
                if not os.path.exists(movies_csv_path):
                    raise FileNotFoundError(f"Missing {movies_csv_path}. Please check path.")

                movies_df = pd.read_csv(movies_csv_path)
                
                # Extract release year from title e.g. "Toy Story (1995)"
                movies_df['release_year'] = movies_df['title'].str.extract(r'\((\d{4})\)$')[0].astype('Int32')
                movies_df['clean_title'] = movies_df['title'].str.replace(r'\s*\(\d{4}\)$', '', regex=True).str.strip()
                
                # Load dim_movies
                buf_movies = io.StringIO()
                movies_df[['movieId', 'clean_title', 'release_year']].to_csv(
                    buf_movies, sep='\t', index=False, header=False, na_rep='\\N'
                )
                fast_copy(cur, 'dim_movies', ['movie_id', 'title', 'release_year'], buf_movies)
                conn.commit()
                print(f" -> Successfully loaded {len(movies_df):,} movies into dim_movies.")

                # Explode genres for 1NF
                genre_series = movies_df['genres'].str.split('|').explode().str.strip()
                unique_genres = sorted([g for g in genre_series.unique() if g and g != '(no genres listed)'])
                genre_map = {name: idx + 1 for idx, name in enumerate(unique_genres)}
                
                # Load dim_genres
                genre_df = pd.DataFrame(list(genre_map.items()), columns=['genre_name', 'genre_id'])
                buf_genres = io.StringIO()
                genre_df[['genre_id', 'genre_name']].to_csv(buf_genres, sep='\t', index=False, header=False)
                fast_copy(cur, 'dim_genres', ['genre_id', 'genre_name'], buf_genres)
                conn.commit()
                print(f" -> Successfully loaded {len(genre_df)} genres into dim_genres.")

                # Load bridge_movie_genre
                exploded = movies_df[['movieId', 'genres']].copy()
                exploded['genre_name'] = exploded['genres'].str.split('|')
                exploded = exploded.explode('genre_name')
                exploded['genre_id'] = exploded['genre_name'].map(genre_map)
                bridge_df = exploded.dropna(subset=['genre_id'])[['movieId', 'genre_id']].drop_duplicates().copy()
                bridge_df['movieId'] = bridge_df['movieId'].astype('int32')
                bridge_df['genre_id'] = bridge_df['genre_id'].astype('int32')
                
                buf_bridge = io.StringIO()
                bridge_df.to_csv(buf_bridge, sep='\t', index=False, header=False)
                fast_copy(cur, 'bridge_movie_genre', ['movie_id', 'genre_id'], buf_bridge)
                conn.commit()
                print(f" -> Successfully loaded {len(bridge_df):,} relationships into bridge_movie_genre.")

            # ---------------------------------------------------------
            # 2. Dim Date (Temporal Dimension)
            # ---------------------------------------------------------
            cur.execute("SELECT count(*) FROM dim_date;")
            date_count = cur.fetchone()[0]
            if date_count > 0:
                print(f"\n[Step 2/5] dim_date already has {date_count:,} dates. Skipping...")
            else:
                print("\n[Step 2/5] Synthesizing & Ingesting Dim Date...")
                date_range = pd.date_range(start='1990-01-01', end='2026-12-31', freq='D')
                dim_date = pd.DataFrame({
                    'date_key': date_range.strftime('%Y%m%d').astype(int),
                    'full_date': date_range.strftime('%Y-%m-%d'),
                    'year': date_range.year,
                    'quarter': date_range.quarter,
                    'month': date_range.month,
                    'day': date_range.day
                })
                buf_date = io.StringIO()
                dim_date.to_csv(buf_date, sep='\t', index=False, header=False)
                fast_copy(cur, 'dim_date', ['date_key', 'full_date', 'year', 'quarter', 'month', 'day'], buf_date)
                conn.commit()
                print(f" -> Successfully loaded {len(dim_date):,} dates into dim_date.")

            # ---------------------------------------------------------
            # 3. Dim Users
            # ---------------------------------------------------------
            cur.execute("SELECT count(*) FROM dim_users;")
            users_count = cur.fetchone()[0]
            if users_count > 0:
                print(f"\n[Step 3/5] dim_users already has {users_count:,} users. Skipping...")
            else:
                print("\n[Step 3/5] Extracting & Ingesting Dim Users from ratings.csv...")
                ratings_csv_path = 'ml-32m/ratings.csv'
                t_users = time.time()
                user_series = pd.read_csv(ratings_csv_path, usecols=['userId'], dtype='int32')['userId'].unique()
                users_df = pd.DataFrame({'user_id': sorted(user_series)})
                buf_users = io.StringIO()
                users_df.to_csv(buf_users, sep='\t', index=False, header=False)
                fast_copy(cur, 'dim_users', ['user_id'], buf_users)
                conn.commit()
                print(f" -> Successfully loaded {len(users_df):,} users into dim_users in {time.time() - t_users:.2f}s.")

            # ---------------------------------------------------------
            # 4. Fact Ratings (32 Million rows)
            # ---------------------------------------------------------
            if ratings_count >= 32000000:
                print(f"\n[Step 4/5] fact_ratings ALREADY COMPLETE ({ratings_count:,} rows)! Skipping...")
            else:
                print(f"\n[Step 4/5] Ingesting 32M Fact Ratings (currently {ratings_count:,})...")
                cur.execute("TRUNCATE TABLE fact_ratings;")
                conn.commit()
                t_ratings = time.time()
                chunk_size = 2_000_000
                total_loaded = 0
                ratings_csv_path = 'ml-32m/ratings.csv'

                for chunk_idx, chunk in enumerate(pd.read_csv(ratings_csv_path, chunksize=chunk_size)):
                    t_chunk = time.time()
                    dt = pd.to_datetime(chunk['timestamp'], unit='s')
                    chunk['date_key'] = (dt.dt.year * 10000 + dt.dt.month * 100 + dt.dt.day).astype('int32')
                    
                    buf_ratings = io.StringIO()
                    chunk[['userId', 'movieId', 'date_key', 'rating']].to_csv(
                        buf_ratings, sep='\t', index=False, header=False
                    )
                    fast_copy(cur, 'fact_ratings', ['user_id', 'movie_id', 'date_key', 'rating'], buf_ratings)
                    conn.commit()
                    total_loaded += len(chunk)
                    print(f" -> Chunk {chunk_idx + 1:2d}: {len(chunk):,} rows loaded in {time.time() - t_chunk:5.1f}s | Progress: {total_loaded:,} / 32M")
                
                print(f" -> All {total_loaded:,} fact ratings loaded in {time.time() - t_ratings:.1f}s.")

            # ---------------------------------------------------------
            # 5. Fact Tags
            # ---------------------------------------------------------
            cur.execute("SELECT count(*) FROM fact_tags;")
            tags_count = cur.fetchone()[0]
            if tags_count > 0:
                print(f"\n[Step 5/5] fact_tags already has {tags_count:,} rows. Skipping...")
            else:
                tags_csv_path = 'ml-32m/tags.csv'
                if os.path.exists(tags_csv_path):
                    print("\n[Step 5/5] Ingesting Fact Tags...")
                    t_tags = time.time()
                    tags_df = pd.read_csv(tags_csv_path)
                    
                    # Clean tag text: strip, remove delimiters, and remove backslashes (which escape newlines in COPY)
                    tags_df['tag_clean'] = (
                        tags_df['tag']
                        .astype(str)
                        .str.replace('\\', '', regex=False)
                        .str.replace(r'[\t\r\n]+', ' ', regex=True)
                        .str.strip()
                    )
                    tags_df = tags_df[tags_df['tag_clean'].str.len() > 0]
                    
                    dt_tags = pd.to_datetime(tags_df['timestamp'], unit='s')
                    tags_df['date_key'] = (dt_tags.dt.year * 10000 + dt_tags.dt.month * 100 + dt_tags.dt.day).astype('int32')
                    
                    buf_tags = io.StringIO()
                    tags_df[['userId', 'movieId', 'date_key', 'tag_clean']].to_csv(
                        buf_tags, sep='\t', index=False, header=False
                    )
                    fast_copy(cur, 'fact_tags', ['user_id', 'movie_id', 'date_key', 'tag'], buf_tags)
                    conn.commit()
                    print(f" -> Successfully loaded {len(tags_df):,} tags in {time.time() - t_tags:.2f}s.")

            # ---------------------------------------------------------
            # 6. Genome Relevance (If files are available)
            # ---------------------------------------------------------
            gt_path = 'ml-32m/genome-tags.csv'
            gs_path = 'ml-32m/genome-scores.csv'

            if os.path.exists(gt_path):
                print("\n[Bonus] Ingesting Dim Genome Tags...")
                gt_df = pd.read_csv(gt_path)
                buf_gt = io.StringIO()
                gt_df[['tagId', 'tag']].to_csv(buf_gt, sep='\t', index=False, header=False)
                fast_copy(cur, 'dim_genome_tags', ['tag_id', 'tag'], buf_gt)
                conn.commit()
                print(f" -> Successfully loaded {len(gt_df):,} genome tags.")

            if os.path.exists(gs_path):
                print("\n[Bonus] Ingesting Fact Genome Scores (Streaming COPY)...")
                t_gs = time.time()
                for i, chunk in enumerate(pd.read_csv(gs_path, chunksize=2_000_000)):
                    buf_gs = io.StringIO()
                    chunk[['movieId', 'tagId', 'relevance']].to_csv(buf_gs, sep='\t', index=False, header=False)
                    fast_copy(cur, 'fact_genome_scores', ['movie_id', 'tag_id', 'relevance'], buf_gs)
                    conn.commit()
                    print(f" -> Genome Chunk {i + 1}: loaded {len(chunk):,} rows.")
                print(f" -> Successfully loaded genome scores in {time.time() - t_gs:.1f}s.")
            else:
                print("\n[Notice] genome-scores.csv not found in ml-32m/ — skipping genome scores for now.")

    print(f"\n==================================================")
    print(f"  ETL Completed Successfully in {time.time() - start_total:.1f}s! ")
    print(f"==================================================")

if __name__ == '__main__':
    run_etl()
