# Multi-stage production image for the OGRL Next.js frontend (RFC 0003 §8 & §9).

FROM node:24-alpine AS builder
RUN corepack enable

ARG OGRL_API_ORIGIN=http://127.0.0.1:8080
ENV OGRL_API_ORIGIN=${OGRL_API_ORIGIN}

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM node:24-alpine AS runtime
RUN corepack enable \
    && addgroup -S nextjs \
    && adduser -S nextjs -G nextjs

WORKDIR /app
ENV NODE_ENV=production \
    OGRL_API_ORIGIN="http://127.0.0.1:8080" \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

COPY --from=builder --chown=nextjs:nextjs /app/package.json ./
COPY --from=builder --chown=nextjs:nextjs /app/next.config.ts ./
COPY --from=builder --chown=nextjs:nextjs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nextjs /app/.next ./.next

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["pnpm", "start"]
