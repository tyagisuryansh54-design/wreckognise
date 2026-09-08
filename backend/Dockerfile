# Wreckognise API -- portable container for Render / Railway / Fly / Cloud Run.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# opencv-python-headless still links against libglib; nothing else is needed
# because the headless wheel drops the GUI/X11 dependencies.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first so the dependency layer caches across code changes.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
# Trained detector weights + the validation figures measured alongside them.
COPY models ./models
# Bundled real sonar images for the dashboard's held-out sample button.
COPY samples ./samples
RUN mkdir -p storage/uploads storage/processed storage/reports

EXPOSE 8000

# Hosts inject the port to bind. Default to 8000 for a plain `docker run`.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
