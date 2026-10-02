FROM kong:3.9.3
USER root
COPY kong/plugins/watcher /usr/local/share/lua/5.1/kong/plugins/watcher
USER kong
ENV KONG_PLUGINS=bundled,watcher
