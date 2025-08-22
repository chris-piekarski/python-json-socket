# Behave environment hooks for setup/teardown safety

def after_all(context):
    # Best-effort cleanup in case scenarios fail mid-run
    server = getattr(context, 'jsonserver', None)
    client = getattr(context, 'jsonclient', None)
    try:
        if client is not None:
            client.close()
    except Exception:  # pragma: no cover - cleanup best-effort
        pass
    try:
        if server is not None:
            server.stop()
            server.join(timeout=3)
    except Exception:  # pragma: no cover
        pass

