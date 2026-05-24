FROM nginx:alpine

# envsubst lives in gettext
RUN apk add --no-cache gettext

# Default backend URL (overridable at runtime: -e BACKEND_URL=...)
ENV BACKEND_URL=http://localhost:8080

# Copy the unmodified template — it contains the literal token __BACKEND_URL__
COPY index.html /usr/share/nginx/html/index.html.template

# Replace the token at container start, then hand off to nginx
RUN printf '%s\n' \
        '#!/bin/sh' \
        'set -e' \
        'echo "[entrypoint] Substituting BACKEND_URL=$BACKEND_URL"' \
        'envsubst "\$BACKEND_URL" < /usr/share/nginx/html/index.html.template \
          | sed "s|__BACKEND_URL__|$BACKEND_URL|g" \
          > /usr/share/nginx/html/index.html' \
        'exec nginx -g "daemon off;"' \
        > /docker-entrypoint.d/40-substitute-backend-url.sh \
    && chmod +x /docker-entrypoint.d/40-substitute-backend-url.sh

EXPOSE 80
