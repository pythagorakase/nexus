"""NEXUS HTTP API package.

The package exports nothing. Importing ``nexus.api`` or any helper/schema
submodule must stay free of runtime side effects: no FastAPI app
construction, no database pools, and no schema checks (issue #369). The one
application is the gateway, ``nexus.api.narrative:app`` (issue #807).
"""
