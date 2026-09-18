.PHONY: build up down logs ps restart shell health rebuild prune

# Local (WSL) and server use the same commands.

build:            ## Build both images
	docker compose build

up:               ## Start in the background
	docker compose up -d

down:             ## Stop and remove containers
	docker compose down

restart:          ## Restart without rebuilding
	docker compose restart

rebuild:          ## Rebuild from scratch and restart (use after a code change)
	docker compose build --no-cache && docker compose up -d

logs:             ## Follow logs from both services
	docker compose logs -f --tail=100

ps:               ## Show container status and health
	docker compose ps

shell:            ## Shell into the backend container
	docker compose exec backend sh

health:           ## Hit the health endpoint through nginx
	curl -fsS http://localhost/api/health && echo "  <- backend OK via nginx"

prune:            ## Reclaim disk from old images and build cache
	docker system prune -af --volumes
