"""Test import of alternative_content router."""
try:
    from api.routers import alternative_content
    print("Import successful!")
    print(f"Router prefix: {alternative_content.router.prefix}")
    print(f"Routes: {len(alternative_content.router.routes)}")
    for route in alternative_content.router.routes:
        print(f"  - {route.methods} {route.path}")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
