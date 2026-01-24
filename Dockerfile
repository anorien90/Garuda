# Use an official lightweight Python image, target 3.10+
FROM python:3.13-slim

# Install Chrome & Chromedriver
RUN apt-get update
RUN apt-get install -y wget unzip fonts-liberation libappindicator3-1 libasound2 libnspr4 libnss3 libxss1 libxtst6 xdg-utils libgbm-dev
RUN apt-get update && \
    apt-get install -y wget unzip gnupg2 ca-certificates fonts-liberation libappindicator3-1 libasound2 libnspr4 libnss3 libxss1 libxtst6 xdg-utils && \
    wget -O- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    CHROMEDRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE) && \
    wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    rm /tmp/chromedriver.zip && \
    chmod +x /usr/local/bin/chromedriver && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set display port to avoid crashes
ENV DISPLAY=:99

WORKDIR /app

# Copy dependencies and entry points
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the default Flask port
EXPOSE 5000

# Set environment variables (override in docker-compose/.env)
ENV GARUDA_UI_API_KEY=changeme
ENV GARUDA_DB_URL=sqlite:///crawler.db

# Default command to run the webapp (override as needed)
CMD ["python", "-m", "src.webapp.app"]
