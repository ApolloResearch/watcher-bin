"""Watcher external processor for Agent Router (formerly Envoy AI Gateway).

Run ``watcher-agent-router serve`` next to the gateway and attach it with the
``EnvoyExtensionPolicy`` in ``gateway/agent-router.yaml``. Gateway clients do
not import this package.
"""
