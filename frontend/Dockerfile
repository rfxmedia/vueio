FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.js ./
COPY scripts/generate-third-party-notices.mjs ./scripts/generate-third-party-notices.mjs
COPY src ./src
COPY nginx.conf nginx-api-proxy.conf ./
RUN mkdir -p public && \
    node ./scripts/generate-third-party-notices.mjs ./public/THIRD_PARTY_NOTICES.txt && \
    chmod 0444 nginx.conf nginx-api-proxy.conf && \
    npm run build

FROM nginxinc/nginx-unprivileged:1.31.3-alpine3.24@sha256:f972e5322b9797dc2a6b830030094426437b1ae7032e4644496395336ac6fdac
USER root
RUN apk upgrade --no-cache
LABEL org.opencontainers.image.title="Vue.io UI" \
      org.opencontainers.image.licenses="PolyForm-Perimeter-1.0.1" \
      org.opencontainers.image.url="https://polyformproject.org/licenses/perimeter/1.0.1"
ENV VUEIO_TRUST_UPSTREAM_PROXY=false
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/nginx-api-proxy.conf /etc/nginx/vueio-api-proxy.inc
USER 101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
