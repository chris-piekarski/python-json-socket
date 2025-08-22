# Behave environment hooks for setup/teardown safety

def after_scenario(context, scenario):
    # Per-scenario cleanup for isolation
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

def after_all(context):
    # Redundant cleanup in case anything leaked between scenarios
    after_scenario(context, None)
