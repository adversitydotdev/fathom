"""Use-cases: the business rules between a caller and the kernel and stores.

No FastAPI, no SQL. Each service depends on narrow repository protocols it
declares itself, and takes a `Principal` on every call.
"""
