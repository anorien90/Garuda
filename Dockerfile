FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y wget unzip gnupg2 ca-certificates fonts-liberation libappindicator3-1 libasound2 libnspr4 libnss3 libxss1 libxtst6 xdg-utils curl

# Add Chrome repo & install Chrome
RUN wget -O- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg \
  && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update \
  && apt-get install -y google-chrome-stable

# Get matching ChromeDriver version
ARG CHROME_MAJOR=144
RUN CHROMEDRIVER_VERSION=$(curl -sSL "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_MAJOR}") \
  && wget -O /tmp/chromedriver.zip "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" \
  && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
  && mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
  && rm -rf /usr/local/bin/chromedriver-linux64 /tmp/chromedriver.zip \
  && chmod +x /usr/local/bin/chromedriver

# Clean up to make image smaller and avoid bugs
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# (rest of your Dockerfile unchanged)
WORKDIR /app

# Copy dependencies and entry points
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data
COPY ./src/ ./src/
COPY ./.env .
COPY ./docker-compose.yml .
COPY ./pyproject.toml .
COPY ./README.md .
COPY ./LICENSE .

RUN pip install --no-cache-dir .
RUN apt-get update && apt-get install -y tesseract-ocr
RUN pip install --no-cache-dir PyPDF2
# Expose the default Flask port
EXPOSE 8080

# Set environment variables (override in docker-compose/.env)
ENV GARUDA_UI_API_KEY=changeme
ENV GARUDA_DB_URL=sqlite:////app/data/crawler.db

# Default command to run the webapp (override as needed)
CMD ["garuda-intel-webapp"]
