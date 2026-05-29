FROM python:3.11-slim

WORKDIR /app

# Install system dependencies, Node.js, and npm
RUN apt-get update && apt-get install -y \
    build-essential \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Antigravity (Gemini) CLI globally
RUN npm install -g @google/gemini-cli

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment setup
ENV PYTHONPATH=/app

# Expose UI port
EXPOSE 8080

# Command to run the unified server (UI + Telegram Bot)
CMD ["python", "-m", "src.api.server"]
