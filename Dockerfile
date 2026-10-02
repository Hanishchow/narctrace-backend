FROM python:3.11-slim

WORKDIR /app

# System deps for opencv-headless and scikit-image
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate demo data at build time so first request is instant
RUN python -c "from app.demo_data import generate_all_demo_samples; generate_all_demo_samples()"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
