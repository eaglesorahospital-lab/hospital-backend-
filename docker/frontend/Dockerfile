# ==============================================================================
# Frontend Production Containerfile (Phase 17 — Production Deployment)
# ==============================================================================
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Build production Vite bundle
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

EXPOSE 3000

# Run Vite production preview server
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
