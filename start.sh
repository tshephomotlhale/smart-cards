#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[smart-cards]${NC} $1"; }
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     Smart Patient Card System            ║${NC}"
echo -e "${BOLD}║     Startup Script                       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Check Docker is running ─────────────────────────────────────────────
log "Checking Docker..."
if ! docker info > /dev/null 2>&1; then
  fail "Docker is not running. Please start Docker Desktop and try again."
fi
ok "Docker is running"

# ── 2. Set up .env if missing ──────────────────────────────────────────────
log "Checking environment config..."
if [ ! -f "$ROOT/backend/.env" ]; then
  warn ".env not found — copying from .env.example"
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"

  # Generate a random SECRET_KEY
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
           python -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s|change_me_to_a_long_random_string_in_production|$SECRET|g" "$ROOT/backend/.env"
  ok ".env created with a generated SECRET_KEY"
  warn "Edit backend/.env and add your Africa's Talking API key (AT_API_KEY) for USSD/SMS"
else
  ok ".env already exists"
fi

# ── 3. Build and start containers ──────────────────────────────────────────
log "Building and starting containers (db, redis, api)..."
docker compose -f "$ROOT/docker-compose.yml" up --build -d

# ── 4. Wait for PostgreSQL to be healthy ───────────────────────────────────
log "Waiting for PostgreSQL to be ready..."
ATTEMPTS=0
MAX=30
until docker compose -f "$ROOT/docker-compose.yml" exec -T db pg_isready -U smartcards -q 2>/dev/null; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ $ATTEMPTS -ge $MAX ]; then
    fail "PostgreSQL did not become ready in time. Check: docker compose logs db"
  fi
  sleep 2
done
ok "PostgreSQL is ready"

# ── 5. Wait for Redis to be healthy ────────────────────────────────────────
log "Waiting for Redis to be ready..."
ATTEMPTS=0
until docker compose -f "$ROOT/docker-compose.yml" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ $ATTEMPTS -ge $MAX ]; then
    fail "Redis did not become ready in time. Check: docker compose logs redis"
  fi
  sleep 2
done
ok "Redis is ready"

# ── 6. Wait for API to be healthy ──────────────────────────────────────────
log "Waiting for API to be ready..."
ATTEMPTS=0
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ $ATTEMPTS -ge $MAX ]; then
    fail "API did not become ready in time. Check: docker compose logs api"
  fi
  sleep 2
done
ok "API is ready"

# ── 7. Seed database (only on first run) ───────────────────────────────────
log "Checking if database needs seeding..."
SEEDED=$(docker compose -f "$ROOT/docker-compose.yml" exec -T db \
  psql -U smartcards -d smartcards -tAc \
  "SELECT COUNT(*) FROM facilities;" 2>/dev/null || echo "0")

SEEDED=$(echo "$SEEDED" | tr -d '[:space:]')

if [ "$SEEDED" = "0" ] || [ -z "$SEEDED" ]; then
  log "Seeding database with facilities and medicines..."
  docker compose -f "$ROOT/docker-compose.yml" exec -T api \
    python -m app.db.seed
  ok "Database seeded"
else
  ok "Database already seeded ($SEEDED facilities found)"
fi

# ── 8. Done ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Everything is running!${NC}"
echo ""
echo -e "  ${BOLD}API${NC}          →  http://localhost:8000"
echo -e "  ${BOLD}API Docs${NC}     →  http://localhost:8000/docs"
echo -e "  ${BOLD}Health check${NC} →  http://localhost:8000/health"
echo -e "  ${BOLD}Admin login${NC}  →  admin@smartcards.bw / Admin1234!"
echo ""
echo -e "${YELLOW}  Remember to change the admin password before demo!${NC}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "  docker compose logs -f api     # stream API logs"
echo -e "  docker compose logs -f         # stream all logs"
echo -e "  docker compose down            # stop everything"
echo -e "  docker compose down -v         # stop + wipe all data"
echo ""
