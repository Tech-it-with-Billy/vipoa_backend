"""
Test Summary Runner
Runs all unit tests and displays results
"""
import subprocess
import sys

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

# Run API tests
print("\n1️⃣  API Tests (User Registration, Login, Profile)")
print("-" * 70)
result = subprocess.run(
    [sys.executable, 'manage.py', 'test', 'api.tests', '--keepdb', '-v', '2'],
    capture_output=True,
    text=True
)

# Extract summary
lines = result.stderr.split('\n')
for line in lines[-20:]:
    if line.strip():
        print(line)

# Run Jema tests if they exist
print("\n\n2️⃣  Jema AI Tests (Chat, Sessions, Recipes)")
print("-" * 70)
result2 = subprocess.run(
    [sys.executable, 'manage.py', 'test', 'jema.tests.test_api', '--keepdb', '-v', '2'],
    capture_output=True,
    text=True,
    timeout=60
)

# Extract summary
lines2 = result2.stderr.split('\n')
for line in lines2[-20:]:
    if line.strip():
        print(line)

print("\n" + "=" * 70)
print("✅ Test Run Complete")
print("=" * 70)
