#!/bin/bash

echo "Running prestart.sh script..."

# Run database migrations
poetry run python manage.py migrate --noinput

echo "Migrations complete. Prestart script finished."