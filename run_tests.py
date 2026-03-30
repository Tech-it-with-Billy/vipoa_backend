"""
Test Summary Runner
Runs all unit tests and displays results
"""
import subprocess
import sys
import os

# ensure development dependencies are available; this makes the script
# self‑bootstrapping when someone runs it on a clean checkout.
try:
    import dj_database_url  # noqa: F401
    import whitenoise  # noqa: F401
except ImportError:
    print("dependencies missing, installing from requirements.txt")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

print("=" * 70)
print("🧪 RUNNING UNIT TESTS FOR VIPOA API")
print("=" * 70)

# Set environment variables for testing - disable SSL redirect
os.environ['DEBUG'] = 'True'
os.environ['DJANGO_SETTINGS_MODULE'] = 'vipoa_backend.settings'

# Import Django here so settings are loaded with DEBUG=True
import django
django.setup()

# Run Jema tests
print("\n1️⃣  Jema AI Tests (Chat, Sessions, Recipes)")
print("-" * 70)
result = subprocess.run(
    [
        sys.executable, 'manage.py', 'test', 
        'jema.tests.test_api', 
        '--keepdb', 
        '-v', '2'
    ],
    timeout=60,
    env={**os.environ, 'DEBUG': 'True'}
)

print("\n" + "=" * 70)
if result.returncode == 0:
    print("✅ Test Run Complete - All Tests Passed!")
else:
    print("⚠️  Test Run Complete - Some Tests Failed")
    print("   Run: python manage.py test jema.tests.test_api -v 2")
    print("   for more detailed output")
print("=" * 70)
