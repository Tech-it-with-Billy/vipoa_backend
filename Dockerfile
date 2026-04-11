# Base image
FROM python:3.11-slim

# Prevent Python from writing pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project files
COPY . .

# Expose the port Railway expects
EXPOSE 8080

# Collect static files, run migrations, and start Gunicorn at runtime so that
# Railway's environment variables (SECRET_KEY, DATABASE_URL, etc.) are available.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate && gunicorn vipoa_backend.wsgi:application --bind 0.0.0.0:$PORT"]