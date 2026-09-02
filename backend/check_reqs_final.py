with open('requirements.txt', 'r') as f:
    reqs = f.read().lower()

pkgs = [
    'modal', 'supabase', 'boto3', 'httpx', 'librosa', 'scipy',
    'soundfile', 'pydub', 'PIL', 'PIL.Image', 'sqlalchemy',
    'sentry_sdk', 'email_validator', 'multipart', 'pypinyin',
    'pydub', 'pillow', 'librosa', 'scipy', 'numpy', 'mido',
    'uvicorn', 'fastapi', 'pydantic', 'email_validator',
    'supabase', 'boto3', 'aiohttp', 'httpx', 'numpy',
    'scipy', 'librosa', 'python-multipart', 'pypinyin',
    'sqlalchemy', 'sentry_sdk', 'soundfile', 'pydub',
    'pillow', 'modal', 'python-dotenv', 'uvicorn'
]

with open('requirements.txt', 'r') as f:
    reqs = f.read().lower()

print('=== Requirements Check ===')
for pkg in sorted(set([
    'modal', 'supabase', 'boto3', 'httpx', 'librosa', 'scipy',
    'soundfile', 'pydub', 'PIL', 'PIL.Image', 'sqlalchemy',
    'sentry_sdk', 'email_validator', 'multipart', 'pypinyin',
    'pydub', 'pillow', 'librosa', 'scipy', 'numpy', 'mido',
    'uvicorn', 'fastapi', 'pydantic', 'email_validator',
    'supabase', 'boto3', 'aiohttp', 'httpx', 'numpy',
    'scipy', 'librosa', 'python-multipart', 'pypinyin',
    'sqlalchemy', 'sentry_sdk', 'soundfile', 'pydub',
    'pillow', 'modal', 'python-dotenv', 'uvicorn'
)):
    found = pkg.lower() in open('requirements.txt').read().lower()
    status = 'OK' if found else 'MISSING'
    print(f'{pkg}: {"OK" if found else "MISSING"}')

print('Done')