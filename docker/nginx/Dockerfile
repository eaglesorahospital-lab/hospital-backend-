# ==============================================================================
# Nginx Reverse Proxy Containerfile (Phase 17 — Production Deployment)
# Multi-stage build compiles React frontend and serves static assets with Nginx
# ==============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:alpine

# Copy built frontend assets to Nginx webroot
COPY --from=frontend-builder /app/dist /var/www/frontend

# Copy Nginx reverse proxy configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Install curl for container healthcheck
RUN apk add --no-cache curl

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
