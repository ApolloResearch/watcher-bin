FROM kong:3.9.3
USER root
COPY kong/plugins/watcher /usr/local/share/lua/5.1/kong/plugins/watcher
USER kong
ENV KONG_PLUGINS=bundled,watcher \
    KONG_PROXY_LISTEN="0.0.0.0:8000 reuseport backlog=16384, 0.0.0.0:8443 ssl reuseport backlog=16384" \
    KONG_ADMIN_LISTEN="127.0.0.1:8001 reuseport backlog=16384, 127.0.0.1:8444 ssl reuseport backlog=16384"
