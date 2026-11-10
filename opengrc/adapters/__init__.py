"""Implementations of the operations' ports against the outside world.

`fetch` reads URLs, `library` checks out library revisions, `git` drives
the git CLI, `blobs` is filesystem object storage, and `secrets` reads the
harness environment. The kernel and the operations never import these; the
composition root does.
"""
