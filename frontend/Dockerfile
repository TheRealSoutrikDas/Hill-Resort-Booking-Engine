# Next.js frontend (D-58). Build context: frontend/.
FROM node:22-slim

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app
RUN chown node:node /app
# Runs as the image's unprivileged `node` user, which also owns .next so the image
# optimiser can write its cache.
USER node

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci

COPY --chown=node:node . .
# The /api/* rewrite target is fixed at build time (next.config.ts), so API_URL must be
# set for the build as well as at runtime. Railway passes service variables to ARGs.
ARG API_URL
RUN npm run build

# next start listens on $PORT, which Railway sets.
CMD ["npm", "run", "start"]
