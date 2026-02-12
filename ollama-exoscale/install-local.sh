#!/bin/bash
# Complete Ollama Installation Script for Exoscale Ubuntu 24.04 LTS
# Installs all dependencies including NVIDIA Container Toolkit for GPU support

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
OLLAMA_MODEL="${OLLAMA_MODEL:-granite3.1-dense:8b}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-8192}"

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo "================================================"
echo "  Ollama + NVIDIA Installation for Exoscale"
echo "  Ubuntu 24.04 LTS"
echo "================================================"
echo ""
print_info "Model: $OLLAMA_MODEL"
print_info "Port: $OLLAMA_PORT"
print_info "Context Length: $OLLAMA_CONTEXT_LENGTH"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Clean up any broken repository files
print_step "Cleaning up previous installation attempts..."
rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list
rm -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
print_info "Cleanup complete"

# Update system
print_step "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# Install base dependencies
print_step "Installing base dependencies..."
apt-get install -y -qq \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    apt-transport-https \
    wget \
    pciutils

# Detect GPU
print_step "Detecting hardware..."
HAS_GPU=false
if lspci | grep -i nvidia >/dev/null 2>&1; then
    GPU_NAME=$(lspci | grep -i nvidia | head -1 | cut -d: -f3 | xargs)
    print_info "✓ NVIDIA GPU detected: $GPU_NAME"
    HAS_GPU=true
else
    print_info "No NVIDIA GPU detected - will install CPU-only version"
fi

# Install Docker
if command_exists docker; then
    print_info "✓ Docker already installed: $(docker --version)"
else
    print_step "Installing Docker Engine..."
    
    # Add Docker GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    apt-get update -qq
    apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
    
    print_info "✓ Docker installed: $(docker --version)"
fi

# Enable and start Docker
print_step "Configuring Docker service..."
systemctl enable docker
systemctl start docker
print_info "✓ Docker service running"

# Install NVIDIA drivers and Container Toolkit if GPU detected
if [ "$HAS_GPU" = true ]; then
    print_step "Installing NVIDIA drivers..."
    
    # Check if driver is already installed
    if command_exists nvidia-smi; then
        if nvidia-smi >/dev/null 2>&1; then
            DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
            print_info "✓ NVIDIA driver already installed: $DRIVER_VERSION"
        else
            print_warning "NVIDIA driver installed but not loaded - reboot required"
        fi
    else
        print_info "Installing NVIDIA driver 535..."
        apt-get install -y -qq nvidia-driver-535
        print_warning "NVIDIA driver installed - reboot required to activate"
    fi
    
    # Install NVIDIA Container Toolkit
    print_step "Installing NVIDIA Container Toolkit..."
    
    if dpkg -l | grep -q nvidia-container-toolkit; then
        print_info "✓ NVIDIA Container Toolkit already installed"
    else
        print_info "Adding NVIDIA Container Toolkit repository..."
        
        # Add repository GPG key
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
            gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        
        # Add repository list
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        
        apt-get update -qq
        apt-get install -y -qq nvidia-container-toolkit
        
        print_info "✓ NVIDIA Container Toolkit installed"
    fi
    
    # Configure Docker to use NVIDIA runtime
    print_step "Configuring Docker for NVIDIA GPU..."
    nvidia-ctk runtime configure --runtime=docker --set-as-default
    systemctl restart docker
    print_info "✓ Docker configured for GPU support"
fi

# Pull Ollama Docker image
print_step "Pulling Ollama Docker image..."
docker pull ollama/ollama:latest
print_info "✓ Ollama image downloaded"

# Stop and remove existing Ollama container
if docker ps -a --format '{{.Names}}' | grep -q '^ollama$'; then
    print_info "Removing existing Ollama container..."
    docker stop ollama 2>/dev/null || true
    docker rm ollama 2>/dev/null || true
fi

# Start Ollama container
print_step "Starting Ollama container..."

if [ "$HAS_GPU" = true ] && command_exists nvidia-smi && nvidia-smi >/dev/null 2>&1; then
    print_info "Starting with GPU support..."
    docker run -d \
        --name ollama \
        --restart unless-stopped \
        -p ${OLLAMA_PORT}:11434 \
        -e OLLAMA_CONTEXT_LENGTH=${OLLAMA_CONTEXT_LENGTH} \
        --gpus all \
        -v ollama-data:/root/.ollama \
        ollama/ollama:latest
    print_info "✓ Ollama running with GPU acceleration"
else
    if [ "$HAS_GPU" = true ]; then
        print_warning "GPU detected but driver not active - starting in CPU mode"
        print_warning "Reboot and restart container with: docker restart ollama"
    fi
    print_info "Starting in CPU mode..."
    docker run -d \
        --name ollama \
        --restart unless-stopped \
        -p ${OLLAMA_PORT}:11434 \
        -e OLLAMA_CONTEXT_LENGTH=${OLLAMA_CONTEXT_LENGTH} \
        -v ollama-data:/root/.ollama \
        ollama/ollama:latest
    print_info "✓ Ollama running in CPU mode"
fi

# Wait for Ollama to be ready
print_step "Waiting for Ollama to start..."
for i in {1..30}; do
    if curl -s http://localhost:${OLLAMA_PORT}/ >/dev/null 2>&1; then
        print_info "✓ Ollama is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "Ollama failed to start"
        docker logs ollama --tail 50
        exit 1
    fi
    sleep 1
done

# Pull the model
if [ -n "$OLLAMA_MODEL" ]; then
    print_step "Pulling model: $OLLAMA_MODEL"
    print_warning "This may take several minutes..."
    docker exec ollama ollama pull "$OLLAMA_MODEL"
    print_info "✓ Model downloaded"
fi

# Create helper scripts
print_step "Creating helper scripts..."

cat > /usr/local/bin/ollama <<'EOFSCRIPT'
#!/bin/bash
docker exec -i ollama ollama "$@"
EOFSCRIPT

cat > /usr/local/bin/ollama-status <<'EOFSCRIPT'
#!/bin/bash
echo "=== Container Status ==="
docker ps -f name=ollama --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "=== Models ==="
docker exec ollama ollama list 2>/dev/null || echo "Container not running"
echo ""
echo "=== Hardware ==="
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    echo "VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)"
    echo "Driver: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
    echo "GPU Usage: $(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader | head -1)"
else
    echo "GPU: Not available"
fi
echo ""
echo "=== API Test ==="
if curl -s http://localhost:11434/ >/dev/null 2>&1; then
    echo "✓ API responding on http://localhost:11434"
else
    echo "✗ API not responding"
fi
EOFSCRIPT

cat > /usr/local/bin/ollama-logs <<'EOFSCRIPT'
#!/bin/bash
docker logs -f ollama
EOFSCRIPT

cat > /usr/local/bin/ollama-restart <<'EOFSCRIPT'
#!/bin/bash
echo "Restarting Ollama..."
docker restart ollama
sleep 3
curl -s http://localhost:11434/ >/dev/null && echo "✓ Ollama restarted" || echo "✗ Ollama not responding"
EOFSCRIPT

chmod +x /usr/local/bin/ollama*

print_info "✓ Helper scripts created"

# Test installation
print_step "Testing installation..."
sleep 2

echo ""
echo "=== Installation Test ==="

# Test API
if curl -s http://localhost:${OLLAMA_PORT}/ >/dev/null 2>&1; then
    print_info "✓ HTTP API responding"
else
    print_error "✗ HTTP API not responding"
fi

# Test CLI
if docker exec ollama ollama list >/dev/null 2>&1; then
    print_info "✓ Ollama CLI working"
else
    print_error "✗ Ollama CLI failed"
fi

# Test model
if docker exec ollama ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
    print_info "✓ Model $OLLAMA_MODEL available"
else
    print_warning "✗ Model not found (may still be downloading)"
fi

# Print summary
echo ""
echo "================================================"
echo "  Installation Complete!"
echo "================================================"
echo ""
echo "📦 Installed Components:"
echo "  - Docker Engine: $(docker --version | cut -d' ' -f3 | tr -d ',')"
if [ "$HAS_GPU" = true ]; then
    if command_exists nvidia-smi && nvidia-smi >/dev/null 2>&1; then
        echo "  - NVIDIA Driver: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
        echo "  - NVIDIA Container Toolkit: $(dpkg -l | grep nvidia-container-toolkit | awk '{print $3}')"
        echo "  - GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    else
        echo "  - NVIDIA Driver: Installed (needs reboot)"
        echo "  - NVIDIA Container Toolkit: Installed"
    fi
fi
echo "  - Ollama: Running on port $OLLAMA_PORT"
echo "  - Model: $OLLAMA_MODEL"
echo ""
echo "🚀 Quick Commands:"
echo "  ollama list              - List installed models"
echo "  ollama pull <model>      - Download a model"
echo "  ollama run <model>       - Run a model interactively"
echo "  ollama-status            - Show system status"
echo "  ollama-logs              - View container logs"
echo "  ollama-restart           - Restart Ollama"
echo ""
echo "🌐 API Endpoints:"
echo "  http://localhost:$OLLAMA_PORT/            - Health check"
echo "  http://localhost:$OLLAMA_PORT/api/generate - Generate endpoint"
echo "  http://localhost:$OLLAMA_PORT/api/chat     - Chat endpoint"
echo "  http://localhost:$OLLAMA_PORT/api/tags     - List models"
echo ""
echo "🐳 Docker Commands:"
echo "  docker logs -f ollama           - View logs"
echo "  docker exec -it ollama bash     - Enter container"
echo "  docker restart ollama           - Restart container"
echo "  docker stop ollama              - Stop container"
echo "  docker start ollama             - Start container"
echo ""

# Check if reboot needed
if [ -f /var/run/reboot-required ]; then
    echo "⚠️  REBOOT REQUIRED"
    echo "================================================"
    print_warning "System needs reboot for kernel/driver updates"
    print_warning "After reboot, Ollama will start automatically"
    echo ""
    if [ "$HAS_GPU" = true ]; then
        print_warning "GPU support will activate after reboot"
        print_warning "Then restart Ollama: docker restart ollama"
    fi
    echo ""
fi

print_info "Installation completed successfully!"

# Show current status
echo ""
ollama-status
