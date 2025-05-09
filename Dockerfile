# Use a base image with Python 3.10, uWSGI, and Nginx
FROM tiangolo/uwsgi-nginx:python3.10

# --- Environment Variables ---
# Set environment variables for the base image's Nginx and uWSGI
ENV UWSGI_INI=/app/uwsgi.ini

# Django's STATIC_URL (usually ends with /)
ENV STATIC_URL=/static/

# The path inside the container where Nginx should find collected static files.
# Aligning with Django's STATIC_ROOT which resolves to /app/staticfiles/
ENV STATIC_PATH=/app/staticfiles/

# Ensure Python output is sent straight to terminal
ENV PYTHONUNBUFFERED=1

# --- System Dependencies (if any) ---
# Example: If you needed libraries for Pillow or psycopg2, you'd install them here.
# RUN apt-get update && apt-get install -y \
#     libpq-dev \
#     jpegoptim optipng pngquant gifsicle \
#     && rm -rf /var/lib/apt/lists/*


# --- Install Poetry ---

# Configure pip to use a regional mirror for faster/more reliable downloads
RUN pip config set global.index-url https://mirrors.tencent.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.tencent.com
    
# Using pip to install Poetry ensures it's available system-wide in the image.
RUN pip install poetry


# --- Application Setup ---
# Set the working directory in the container
WORKDIR /app

# Copy only files needed for dependency installation first for better caching
COPY poetry.lock pyproject.toml ./

# Remove the default PyPI source to ensure mirror is used primarily
# Add the Tencent mirror as the default source named 'tencent'
# RUN poetry source add --priority=default tencent https://mirrors.tencent.com/pypi/simple/




# Configure Poetry to not create a virtual environment within the project directory,
# as the Docker image itself is the isolated environment.
# Install project dependencies using Poetry, excluding the 'dev' group.
# --no-root is used if your pyproject.toml doesn't define the current package as installable (common for Django projects)
RUN poetry config virtualenvs.create false && \
    poetry install --without dev --no-interaction --no-ansi --no-root

# Copy the rest of your Django project into the /app directory in the container
# This includes your Django apps, manage.py, uwsgi.ini, prestart.sh, custom_nginx.conf etc.
COPY . .

# --- Django Specific Commands ---
# Run Django's collectstatic to gather all static files
# This will collect static files into the directory specified by STATIC_ROOT in settings.py
# (which should resolve to /app/staticfiles inside the container).
RUN poetry run python manage.py collectstatic --noinput --clear

# --- Nginx Configuration ---
# Copy custom Nginx site configuration to replace/provide the main site config.
# Ensure your custom_nginx.conf file exists in your project root.
COPY custom_nginx.conf /etc/nginx/conf.d/app.conf

# --- Pre-start Script ---
# Make the prestart.sh script executable.
# The tiangolo base images will automatically run /app/prestart.sh if it exists and is executable
# before starting the main application (uWSGI). This is where migrations are run.
RUN chmod +x /app/prestart.sh

# The base image's entrypoint will handle starting Nginx and uWSGI.
# Nginx listens on port 80 by default.
# uWSGI will be started based on UWSGI_INI.
# CMD is usually inherited from the base image.