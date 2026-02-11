"""Transparent proxy for ``SQLAlchemyStore`` that allows database switching.

All attribute access is forwarded to the *current* underlying store so that
closures that captured the proxy automatically pick up database switches.
"""


class StoreProxy:
    """Delegate every attribute access to the *current* underlying store."""

    def __init__(self, initial):
        object.__setattr__(self, '_target', initial)

    def _swap(self, new_store):
        """Replace the underlying store so all consumers see the new DB."""
        object.__setattr__(self, '_target', new_store)

    # Attribute access is forwarded to the current target ----------------
    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_target'), name)

    def __setattr__(self, name, value):
        if name == '_target':
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, '_target'), name, value)
