"""Test import of main API app."""
try:
    from api.main import app
    print("Import successful!")

    # Find alternative-content routes
    ac_routes = [r for r in app.routes if hasattr(r, 'path') and 'alternative' in r.path]
    print(f"Alternative content routes: {len(ac_routes)}")
    for route in ac_routes:
        methods = getattr(route, 'methods', set())
        print(f"  - {methods} {route.path}")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
