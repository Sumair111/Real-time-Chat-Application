#!/bin/bash
# scripts/docker-dev.sh - Development Environment Script

echo "🚀 Starting ChatFlow Development Environment..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "✅ Please edit .env with your Firebase configuration"
    exit 1
fi

# Check if firebase service account exists
if [ ! -f backend/firebase-service-account.json ]; then
    echo "⚠️  Firebase service account file not found!"
    echo "Please place your firebase-service-account.json in the backend/ directory"
    exit 1
fi

# Build and start development environment
echo "🏗️  Building containers..."
docker-compose -f docker-compose.dev.yml build

echo "🚀 Starting services..."
docker-compose -f docker-compose.dev.yml up -d

echo "📊 Service Status:"
docker-compose -f docker-compose.dev.yml ps

echo ""
echo "✅ Development environment started!"
echo "🌐 Frontend: http://localhost:3000"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo "💾 Redis: localhost:6379"
echo ""
echo "📝 View logs: docker-compose -f docker-compose.dev.yml logs -f"
echo "🛑 Stop: docker-compose -f docker-compose.dev.yml down"

---

#!/bin/bash
# scripts/docker-prod.sh - Production Environment Script

echo "🚀 Starting ChatFlow Production Environment..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    exit 1
fi

# Check if firebase service account exists
if [ ! -f backend/firebase-service-account.json ]; then
    echo "⚠️  Firebase service account file not found!"
    exit 1
fi

# Build and start production environment
echo "🏗️  Building production containers..."
docker-compose build --no-cache

echo "🚀 Starting production services..."
docker-compose up -d

echo "📊 Service Status:"
docker-compose ps

echo ""
echo "✅ Production environment started!"
echo "🌐 Frontend: http://localhost:80"
echo "🔧 Backend API: http://localhost:8000"
echo ""
echo "📝 View logs: docker-compose logs -f"
echo "🛑 Stop: docker-compose down"

---

#!/bin/bash
# scripts/docker-clean.sh - Clean Docker Environment

echo "🧹 Cleaning Docker environment..."

# Stop all containers
echo "🛑 Stopping containers..."
docker-compose -f docker-compose.dev.yml down 2>/dev/null
docker-compose down 2>/dev/null

# Remove containers, networks, images, and volumes
echo "🗑️  Removing containers, networks, and images..."
docker-compose -f docker-compose.dev.yml down --rmi all --volumes --remove-orphans 2>/dev/null
docker-compose down --rmi all --volumes --remove-orphans 2>/dev/null

# Clean up dangling images and containers
echo "🧽 Cleaning up dangling resources..."
docker system prune -f

# Remove specific ChatFlow images
echo "🗑️  Removing ChatFlow images..."
docker images | grep -E "(chatflow|real-time-chat)" | awk '{print $3}' | xargs -r docker rmi -f

echo "✅ Docker environment cleaned!"

---

#!/bin/bash
# scripts/docker-logs.sh - View Docker Logs

if [ "$1" = "prod" ]; then
    echo "📝 Production logs:"
    docker-compose logs -f
else
    echo "📝 Development logs:"
    docker-compose -f docker-compose.dev.yml logs -f
fi

---

#!/bin/bash
# scripts/docker-restart.sh - Restart Services

SERVICE=${1:-all}

if [ "$2" = "prod" ]; then
    COMPOSE_FILE="docker-compose.yml"
    ENV="production"
else
    COMPOSE_FILE="docker-compose.dev.yml"
    ENV="development"
fi

echo "🔄 Restarting $SERVICE in $ENV environment..."

if [ "$SERVICE" = "all" ]; then
    docker-compose -f $COMPOSE_FILE restart
else
    docker-compose -f $COMPOSE_FILE restart $SERVICE
fi

echo "✅ Restart complete!"
docker-compose -f $COMPOSE_FILE ps