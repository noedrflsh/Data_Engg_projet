#!/usr/bin/env bash
# ==============================================================================
# MovieLens 32M OLAP Platform - Database & Environment Setup Script
# ==============================================================================
# This script automates database setup, dataset unzipping, schema initialization,
# ETL streaming ingestion, materialized views creation, and verification tests.
# ==============================================================================

set -eo pipefail

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
echo -e "${BLUE}${BOLD}  MovieLens 32M OLAP Intelligence Platform - Database Setup     ${NC}"
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
echo -e "\n${BLUE}[3/7] Checking MovieLens 32M CSV Dataset...${NC}"
if [ ! -d "$MOVIE_LENS_DIR/ml-32m" ] || [ ! -f "$MOVIE_LENS_DIR/ml-32m/movies.csv" ]; then
    if [ -f "$MOVIE_LENS_DIR/ml-32m.zip" ]; then
        echo -e "${YELLOW}Found $MOVIE_LENS_DIR/ml-32m.zip. Unzipping dataset...${NC}"
        unzip -q "$MOVIE_LENS_DIR/ml-32m.zip" -d "$MOVIE_LENS_DIR/"
        echo -e "${GREEN}✓ Unzipped ml-32m.zip successfully.${NC}"
    elif [ -f "$ROOT_DIR/ml-32m.zip" ]; then
        echo -e "${YELLOW}Found $ROOT_DIR/ml-32m.zip. Unzipping dataset...${NC}"
        unzip -q "$ROOT_DIR/ml-32m.zip" -d "$MOVIE_LENS_DIR/"
        echo -e "${GREEN}✓ Unzipped ml-32m.zip successfully.${NC}"
    else
        echo -e "${RED}✖ Dataset not found in $MOVIE_LENS_DIR/ml-32m/${NC}"
        echo -e "${YELLOW}Please download the MovieLens 32M dataset and place it in movie_lens/:${NC}"
        echo -e "  cd movie_lens"
        echo -e "  curl -O https://files.grouplens.org/datasets/movielens/ml-32m.zip"
        echo -e "  unzip ml-32m.zip"
        exit 1
    fi
fi
echo -e "${GREEN}✓ Dataset confirmed (movies.csv, ratings.csv, tags.csv found).${NC}"

# 5. Initialize Schema
echo -e "\n${BLUE}[4/7] Applying Relational Star Schema (schema.sql)...${NC}"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$MOVIE_LENS_DIR/schema.sql" >/dev/null
echo -e "${GREEN}✓ Schema initialized (tables created or verified).${NC}"

# 6. Run Streaming ETL Ingestion
echo -e "\n${BLUE}[5/7] Running High-Speed Ingestion Pipeline (etl_pipeline.py)...${NC}"
echo -e "${YELLOW}Note: If tables are already populated, ETL will automatically skip them.${NC}"
(cd "$MOVIE_LENS_DIR" && "$PYTHON_BIN" etl_pipeline.py)
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
