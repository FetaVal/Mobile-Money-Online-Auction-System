# Dockerfile for AuctionHub
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project
COPY . /app/

# Collect static files
RUN python manage.py collectstatic --noinput || echo "Static collection will run later"

# Create media directory
RUN mkdir -p /app/media

# Expose port
EXPOSE 5000 8001

# Run migrations and start server
CMD ["sh", "-c", "python manage.py migrate && daphne -b 0.0.0.0 -p 5000 auction_system.asgi:application"]
