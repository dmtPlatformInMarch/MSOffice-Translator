# Use a more comprehensive Debian base image
FROM python/python:3.12.11-bullseye

# Set ENV
ENV PYTHON_VERSION=3.12

# Install Python and necessary tools
# Add Debian Bookworm main and security repositories
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 python3-pip \
    build-essential cmake libreoffice nano net-tools uvicorn && \
    # Fix broken packages and unmet dependencies
    apt-get install -f && \
    # Clean up
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements.txt file into the container at /app
WORKDIR /app
COPY requirements.txt .

# Install any dependencies
ENV ENV_PATH=/app/.env
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Expose port 7979, 17979 to the outside world
EXPOSE 8080

# Run the FastAPI app with Uvicorn
CMD ["python3.12", "document_process.py"]
