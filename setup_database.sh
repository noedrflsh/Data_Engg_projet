#!/usr/bin/env bash
# ==============================================================================
# MovieLens OLAP Platform - Database & Environment Setup Script
# ==============================================================================
# This script automates database setup, dataset unzipping, schema initialization,
# ETL streaming ingestion, materialized views creation, and verification tests.
# Exclusively configured for the MovieLens ml-latest dataset (includes genome scores).
# ==============================================================================

set -eo pipefail

# Argument Parsing
RESET_DB=false
for arg in "$@"; do
    case "$arg" in
        --reset|--clean|-r|--drop-existing)
            RESET_DB=true
            ;;
        --help|-h)
            echo "Usage: ./setup_database.sh [--reset]"
            echo "  --reset   Drop and recreate the database before running ETL from scratch"
            exit 0
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
MOVIE_LENS_DIR="$ROOT_DIR/movie_lens"

# ANSI Color Codes
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m" # No Color

echo -e "${BLUE}${BOLD}=================================================================${NC}"
echo -e "${BLUE}${BOLD}  MovieLens OLAP Intelligence Platform - Database Setup          ${NC}"
echo -e "${BLUE}${BOLD}                (Dataset: MovieLens ml-latest)                   ${NC}"
echo -e "${BLUE}${BOLD}=================================================================${NC}"

# 1. Load Environment Configuration
if [ -f "$ROOT_DIR/.env" ]; then
    echo -e "${GREEN}✓ Loading settings from $ROOT_DIR/.env${NC}"
    # shellcheck disable=SC2046
    export $(grep -v '^#' "$ROOT_DIR/.env" | xargs)
elif [ -f "$MOVIE_LENS_DIR/.env" ]; then
    echo -e "${GREEN}✓ Loading settings from $MOVIE_LENS_DIR/.env${NC}"
    # shellcheck disable=SC2046
    export $(grep -v '^#' "$MOVIE_LENS_DIR/.env" | xargs)
fi

DB_NAME="${DB_NAME:-movie_lens}"
DB_USER="${DB_USER:-gumbo}"
DB_PASSWORD="${DB_PASSWORD:-2836}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

export PGPASSWORD="$DB_PASSWORD"

echo -e "${BLUE}ℹ Target Database Configuration:${NC}"
echo -e "  Host:     ${BOLD}$DB_HOST:$DB_PORT${NC}"
echo -e "  Database: ${BOLD}$DB_NAME${NC}"
echo -e "  User:     ${BOLD}$DB_USER${NC}"
echo ""

# 2. Check Python Environment
echo -e "${BLUE}[1/7] Checking Python Virtual Environment...${NC}"
if [ -d "$ROOT_DIR/.venv" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
    PIP_BIN="$ROOT_DIR/.venv/bin/pip"
    echo -e "${GREEN}✓ Using existing virtualenv in .venv/${NC}"
elif [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_BIN="python3"
    PIP_BIN="pip"
    echo -e "${GREEN}✓ Using active virtualenv: $VIRTUAL_ENV${NC}"
else
    echo -e "${YELLOW}Virtualenv not detected. Creating one in .venv/...${NC}"
    python3 -m venv "$ROOT_DIR/.venv"
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
    PIP_BIN="$ROOT_DIR/.venv/bin/pip"
    echo -e "${GREEN}✓ Virtualenv created.${NC}"
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    "$PIP_BIN" install --upgrade pip
    "$PIP_BIN" install -r "$MOVIE_LENS_DIR/requirements.txt"
    echo -e "${GREEN}✓ Dependencies installed.${NC}"
fi

# 3. Test PostgreSQL Connectivity
echo -e "\n${BLUE}[2/7] Verifying PostgreSQL Connection...${NC}"
if command -v pg_isready >/dev/null 2>&1; then
    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
        echo -e "${RED}✖ PostgreSQL server is not responding at $DB_HOST:$DB_PORT.${NC}"
        echo -e "${YELLOW}Please start your PostgreSQL service first:${NC}"
        echo -e "  - Ubuntu/Debian:  sudo systemctl start postgresql"
        echo -e "  - macOS:          brew services start postgresql@16"
        echo -e "  - Windows:        Start Postgres service via Services application"
        exit 1
    fi
fi

if [ "$RESET_DB" = true ]; then
    echo -e "\n${YELLOW}${BOLD}[Reset Mode] Dropping database '$DB_NAME' and recreating from scratch...${NC}"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE);" >/dev/null 2>&1 || \
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE);" >/dev/null 2>&1 || true

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" >/dev/null 2>&1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" >/dev/null 2>&1 || true

    rm -f "$MOVIE_LENS_DIR/db.sqlite3"
    echo -e "${GREEN}✓ Fresh empty database '$DB_NAME' created.${NC}"
fi

if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' >/dev/null 2>&1; then
    echo -e "${RED}✖ Cannot connect to database '$DB_NAME' as user '$DB_USER'.${NC}"
    echo -e "${YELLOW}The PostgreSQL user or database has not been created yet.${NC}"
    echo -e "To create the default user and database, run the following command in another terminal:"
    echo -e ""
    echo -e "  ${BOLD}sudo -u postgres psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD' SUPERUSER;\"${NC}"
    echo -e "  ${BOLD}sudo -u postgres psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\"${NC}"
    echo -e ""
    echo -e "If you are on macOS with Homebrew (default superuser is your macOS username):"
    echo -e "  ${BOLD}psql -d postgres -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD' SUPERUSER;\"${NC}"
    echo -e "  ${BOLD}psql -d postgres -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\"${NC}"
    echo -e ""
    echo -e "Then rerun this script: ${BOLD}./setup_database.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Successfully connected to PostgreSQL ($DB_NAME as $DB_USER)!${NC}"

# 4. Check Dataset Files
echo -e "\n${BLUE}[3/7] Checking MovieLens ml-latest CSV Dataset...${NC}"
DATASET_RESOLVED=""
if [ -d "$MOVIE_LENS_DIR/ml-latest" ] && [ -f "$MOVIE_LENS_DIR/ml-latest/movies.csv" ] && [ -f "$MOVIE_LENS_DIR/ml-latest/genome-scores.csv" ]; then
    DATASET_RESOLVED="$MOVIE_LENS_DIR/ml-latest"
elif [ -f "$ROOT_DIR/ml-latest.zip" ]; then
    echo -e "${YELLOW}Found $ROOT_DIR/ml-latest.zip. Unzipping dataset into movie_lens/...${NC}"
    unzip -q "$ROOT_DIR/ml-latest.zip" -d "$MOVIE_LENS_DIR/"
    DATASET_RESOLVED="$MOVIE_LENS_DIR/ml-latest"
    echo -e "${GREEN}✓ Unzipped ml-latest.zip successfully.${NC}"
elif [ -f "$MOVIE_LENS_DIR/ml-latest.zip" ]; then
    echo -e "${YELLOW}Found $MOVIE_LENS_DIR/ml-latest.zip. Unzipping dataset into movie_lens/...${NC}"
    unzip -q "$MOVIE_LENS_DIR/ml-latest.zip" -d "$MOVIE_LENS_DIR/"
    DATASET_RESOLVED="$MOVIE_LENS_DIR/ml-latest"
    echo -e "${GREEN}✓ Unzipped ml-latest.zip successfully.${NC}"
else
    echo -e "${RED}✖ ml-latest dataset not found in $MOVIE_LENS_DIR/ml-latest/ or $ROOT_DIR/ml-latest.zip${NC}"
    echo -e "${YELLOW}Please ensure ml-latest.zip is placed at:${NC}"
    echo -e "  $ROOT_DIR/ml-latest.zip"
    echo -e "${YELLOW}(Only ml-latest is used because it provides genome-scores.csv and genome-tags.csv).${NC}"
    exit 1
fi
echo -e "${GREEN}✓ ml-latest dataset confirmed at $DATASET_RESOLVED (all 6 CSVs found including genome scores).${NC}"

# 5. Initialize Schema
echo -e "\n${BLUE}[4/7] Applying Relational Star Schema (schema.sql)...${NC}"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$MOVIE_LENS_DIR/schema.sql" >/dev/null
echo -e "${GREEN}✓ Schema initialized (tables created or verified).${NC}"

# 6. Run Streaming ETL Ingestion
echo -e "\n${BLUE}[5/7] Running High-Speed Ingestion Pipeline (etl_pipeline.py)...${NC}"
echo -e "${YELLOW}Note: If tables are already populated, ETL will automatically skip them.${NC}"
ETL_ARGS=""
if [ "$RESET_DB" = true ]; then
    ETL_ARGS="--reset"
fi
(cd "$MOVIE_LENS_DIR" && "$PYTHON_BIN" etl_pipeline.py $ETL_ARGS)
echo -e "${GREEN}✓ Ingestion verified.${NC}"

# 7. Apply Performance Optimization & Materialized Views
echo -e "\n${BLUE}[6/7] Creating Covering Indexes & Materialized Views (optimize.sql)...${NC}"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$MOVIE_LENS_DIR/optimize.sql" >/dev/null
echo -e "${GREEN}✓ B-Tree covering indexes and Materialized Views ready.${NC}"

# 8. Apply Django Internal Migrations
echo -e "\n${BLUE}[7/7] Applying Django Authentication & Session Migrations...${NC}"
(cd "$MOVIE_LENS_DIR" && "$PYTHON_BIN" manage.py migrate --noinput)
echo -e "${GREEN}✓ Django migrations applied successfully.${NC}"

# 9. Run Verification Test Suite
echo -e "\n${BLUE}=================================================================${NC}"
echo -e "${BLUE}  Running Automated Integration Test Suite...                    ${NC}"
echo -e "${BLUE}=================================================================${NC}"
(cd "$MOVIE_LENS_DIR" && "$PYTHON_BIN" test_suite.py)

echo -e "\n${GREEN}${BOLD}=================================================================${NC}"
echo -e "${GREEN}${BOLD}  🎉 Database & Webapp Setup Completed Successfully!             ${NC}"
echo -e "${GREEN}${BOLD}=================================================================${NC}"
echo -e "You can now launch the web application:"
echo -e "  ${BOLD}cd movie_lens${NC}"
echo -e "  ${BOLD}python manage.py runserver${NC}"
echo -e ""
echo -e "Then open your web browser at: ${BOLD}http://127.0.0.1:8000/${NC}"
echo ""
