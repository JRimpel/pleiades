"""Data access. All SQL used by the API lives in this package; routes stay thin.

Every function borrows a pooled connection via `app.db.get_conn()` unless a `conn` is passed in.
"""
