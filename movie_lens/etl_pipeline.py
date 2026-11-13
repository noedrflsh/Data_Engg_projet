import io
import sys
import time
import os
from pathlib import Path
import zipfile
import pandas as pd
import numpy as np
import psycopg

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

DB_NAME = os.environ.get("DB_NAME", "movie_lens")
DB_USER = os.environ.get("DB_USER", "gumbo")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "2836")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

DB_URI = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

def fast_copy(cur, table_name, columns, buffer):
    buffer.seek(0)
    col_str = ", ".join(columns)
    sql = f"COPY {table_name} ({col_str}) FROM STDIN WITH (FORMAT text)"
    with cur.copy(sql) as copy:
        copy.write(buffer.getvalue())

def resolve_dataset_dir() -> Path:
    """
    Locates the ml-latest dataset directory.
    Automatically extracts ml-latest.zip if the folder does not exist yet.
    """
    # 1. Environment variable override
    env_dir = os.environ.get("DATASET_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir).resolve()

    current_dir = Path.cwd()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    # Candidate directories
    for base in [script_dir, repo_root, current_dir]:
        candidate = base / 'ml-latest'
        if candidate.is_dir() and (candidate / 'movies.csv').exists():
            return candidate.resolve()

    # If directory not found, check for ml-latest.zip archive to auto-unpack
    zip_filename = "ml-latest.zip"
    for base in [repo_root, script_dir, current_dir]:
        zip_path = base / zip_filename
        if zip_path.is_file():
            target_dir = script_dir / 'ml-latest'
            print(f"[Dataset] Found archive: {zip_path}. Unpacking to {script_dir}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(script_dir)
            if target_dir.is_dir() and (target_dir / 'movies.csv').exists():
                return target_dir.resolve()

    raise FileNotFoundError(
        "Could not find MovieLens 'ml-latest' dataset folder or 'ml-latest.zip'. "
        "The project requires 'ml-latest' because only it contains genome-scores and genome-tags. "
        "Please ensure 'ml-latest.zip' is placed in the project root or movie_lens/."
    )

def run_etl():
    print("==================================================")
    print("      MovieLens OLAP High-Speed Ingestion         ")
    print("             (Dataset: ml-latest)                 ")
    print("==================================================")
    start_total = time.time()

    dataset_dir = resolve_dataset_dir()
    print(f"Using dataset from: {dataset_dir}")
    
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            # Handle --reset or --force flags
            if '--reset' in sys.argv or '--force' in sys.argv or os.environ.get("FORCE_RELOAD") == "1":
                print("\n[Reset Mode] Truncating all warehouse tables for clean ingestion...")
                cur.execute("""
                    DO $$ 
                    BEGIN
                        EXECUTE (
                            SELECT 'TRUNCATE TABLE ' || string_agg(quote_ident(tablename), ', ') || ' CASCADE;'
                            FROM pg_tables
                            WHERE schemaname = 'public' 
                              AND tablename IN (
                                  'fact_ratings', 'fact_tags', 'fact_genome_scores',
                                  'dim_genome_tags', 'bridge_movie_genre',
                                  'dim_movies', 'dim_genres', 'dim_users', 'dim_date'
                              )
                        );
                    END $$;
                """)
                conn.commit()
                print(" -> All tables truncated successfully.")

            # Check existing counts to skip already loaded tables
            cur.execute("SELECT count(*) FROM dim_movies;")
            movies_count = cur.fetchone()[0]
            
            cur.execute("SELECT count(*) FROM fact_ratings;")
            ratings_count = cur.fetchone()[0]

            # ---------------------------------------------------------
            # 1. Dim Movies, Dim Genres & Bridge Table
            # ---------------------------------------------------------
            if movies_count > 0:
                print(f"\n[Step 1/6] dim_movies already has {movies_count:,} rows. Skipping...")
            else:
                print("\n[Step 1/6] Ingesting Dim Movies, Genres & Bridge (1NF Normalization)...")
                movies_csv_path = dataset_dir / 'movies.csv'
                if not movies_csv_path.exists():
                    raise FileNotFoundError(f"Missing {movies_csv_path}. Please check dataset.")

                movies_df = pd.read_csv(movies_csv_path)
                
                # Strip title whitespace and extract release year e.g. "Toy Story (1995)"
                movies_df['title'] = movies_df['title'].astype(str).str.strip()
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
                print(f"\n[Step 2/6] dim_date already has {date_count:,} dates. Skipping...")
            else:
                print("\n[Step 2/6] Synthesizing & Ingesting Dim Date...")
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
                print(f"\n[Step 3/6] dim_users already has {users_count:,} users. Skipping...")
            else:
                print("\n[Step 3/6] Extracting & Ingesting Dim Users from ratings.csv...")
                ratings_csv_path = dataset_dir / 'ratings.csv'
                t_users = time.time()
                user_series = pd.read_csv(ratings_csv_path, usecols=['userId'], dtype='int32')['userId'].unique()
                users_df = pd.DataFrame({'user_id': sorted(user_series)})
                buf_users = io.StringIO()
                users_df.to_csv(buf_users, sep='\t', index=False, header=False)
                fast_copy(cur, 'dim_users', ['user_id'], buf_users)
                conn.commit()
                print(f" -> Successfully loaded {len(users_df):,} users into dim_users in {time.time() - t_users:.2f}s.")

            # ---------------------------------------------------------
            # 4. Fact Ratings (~33.8M rows in ml-latest)
            # ---------------------------------------------------------
            if ratings_count >= 33_000_000:
                print(f"\n[Step 4/6] fact_ratings ALREADY COMPLETE ({ratings_count:,} rows)! Skipping...")
            else:
                print(f"\n[Step 4/6] Ingesting Fact Ratings (currently {ratings_count:,} rows)...")
                cur.execute("TRUNCATE TABLE fact_ratings;")
                conn.commit()
                t_ratings = time.time()
                chunk_size = 2_000_000
                total_loaded = 0
                ratings_csv_path = dataset_dir / 'ratings.csv'

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
                    print(f" -> Chunk {chunk_idx + 1:2d}: {len(chunk):,} rows loaded in {time.time() - t_chunk:5.1f}s | Progress: {total_loaded:,} ratings")
                
                print(f" -> All {total_loaded:,} fact ratings loaded in {time.time() - t_ratings:.1f}s.")

            # ---------------------------------------------------------
            # 5. Fact Tags (~2.3M rows in ml-latest)
            # ---------------------------------------------------------
            cur.execute("SELECT count(*) FROM fact_tags;")
            tags_count = cur.fetchone()[0]
            if tags_count > 0:
                print(f"\n[Step 5/6] fact_tags already has {tags_count:,} rows. Skipping...")
            else:
                tags_csv_path = dataset_dir / 'tags.csv'
                if tags_csv_path.exists():
                    print("\n[Step 5/6] Ingesting Fact Tags...")
                    t_tags = time.time()
                    tags_df = pd.read_csv(tags_csv_path)
                    tags_df = tags_df.dropna(subset=['tag'])
                    
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
            # 6. Genome Relevance (Scenario 3a: Top-5 Tag Relevance)
            # ---------------------------------------------------------
            gt_path = dataset_dir / 'genome-tags.csv'
            gs_path = dataset_dir / 'genome-scores.csv'

            if not gt_path.exists() or not gs_path.exists():
                raise FileNotFoundError(
                    f"Missing genome-tags.csv or genome-scores.csv in {dataset_dir}. "
                    "The project requires the ml-latest dataset which includes genome scores."
                )

            cur.execute("SELECT count(*) FROM dim_genome_tags;")
            gt_count = cur.fetchone()[0]
            if gt_count > 0:
                print(f"\n[Step 6/6] dim_genome_tags already has {gt_count:,} rows. Skipping...")
            else:
                print("\n[Step 6/6] Ingesting Dim Genome Tags (genome-tags.csv)...")
                gt_df = pd.read_csv(gt_path)
                buf_gt = io.StringIO()
                gt_df[['tagId', 'tag']].to_csv(buf_gt, sep='\t', index=False, header=False)
                fast_copy(cur, 'dim_genome_tags', ['tag_id', 'tag'], buf_gt)
                conn.commit()
                print(f" -> Successfully loaded {len(gt_df):,} genome tags into dim_genome_tags.")

            cur.execute("SELECT count(*) FROM fact_genome_scores;")
            gs_count = cur.fetchone()[0]
            if gs_count > 0:
                print(f" -> fact_genome_scores already has {gs_count:,} rows. Skipping...")
            else:
                print(" -> Ingesting Fact Genome Scores (genome-scores.csv in 2M chunks)...")
                t_gs = time.time()
                total_gs = 0
                for i, chunk in enumerate(pd.read_csv(gs_path, chunksize=2_000_000)):
                    buf_gs = io.StringIO()
                    chunk[['movieId', 'tagId', 'relevance']].to_csv(buf_gs, sep='\t', index=False, header=False)
                    fast_copy(cur, 'fact_genome_scores', ['movie_id', 'tag_id', 'relevance'], buf_gs)
                    conn.commit()
                    total_gs += len(chunk)
                    print(f"    Genome Chunk {i + 1:2d}: loaded {len(chunk):,} rows | Progress: {total_gs:,}")
                print(f" -> Successfully loaded {total_gs:,} genome scores in {time.time() - t_gs:.1f}s.")

    print(f"\n==================================================")
    print(f"  ETL Completed Successfully in {time.time() - start_total:.1f}s! ")
    print(f"==================================================")

if __name__ == '__main__':
    run_etl()
