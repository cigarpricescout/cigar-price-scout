FROM python:3.11-slim
WORKDIR /app

# Install system dependencies INCLUDING GIT
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p data static/data logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Configure git (will use Railway environment variables)
RUN git config --global user.email "automation@cigarpricescout.com" && \
    git config --global user.name "Price Automation"

# Make automation script executable
RUN chmod +x automation_master.py

# Command to run the automation
CMD ["python", "automation_master.py"]