#!/bin/bash
# scripts/start-prod.sh

echo "🚀 Starting Real-Time Chat App in Production Mode"

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found! Please configure your environment variables."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker."
    exit 1
fi

echo "📦 Building production images..."

# Build and start production services
docker-compose up --build -d

echo "✅ Production environment started!"
echo "🌐 Application: http://localhost:3000"
echo "🔧 Backend API: http://localhost:8000"

# Show running containers
docker-compose ps