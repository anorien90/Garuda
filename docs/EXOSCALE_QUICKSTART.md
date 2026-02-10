# Exoscale Quick Start Guide

## Setup (5 minutes)

### 1. Get Exoscale Credentials
1. Log in to [Exoscale Console](https://portal.exoscale.com)
2. Go to IAM → API Keys
3. Create new key with Compute access
4. Save the API Key and Secret

### 2. Configure Environment
```bash
export EXOSCALE_API_KEY=EXOxxxxxxxxx
export EXOSCALE_API_SECRET=xxxxxxxxxxxx
```

### 3. Start Garuda
```bash
python -m garuda_intel.webapp.app
```

That's it! The Exoscale instance will be created automatically.

## Common Commands

### Check Status
```bash
garuda-exoscale status
```

### Manual Start
```bash
garuda-exoscale start
```

### Manual Stop
```bash
garuda-exoscale stop
```

## Cost Optimization

### Development (aggressive shutdown)
```bash
export EXOSCALE_IDLE_TIMEOUT=600  # 10 minutes
```

### Production (longer running)
```bash
export EXOSCALE_IDLE_TIMEOUT=3600  # 1 hour
```

### Always Running
```bash
export EXOSCALE_IDLE_TIMEOUT=86400  # 24 hours
```

## Instance Types

### CPU (Small Models)
```bash
export EXOSCALE_INSTANCE_TYPE=standard.medium
# Cost: ~$0.05/hour
# Good for: phi3:3.8b, granite3.1-dense:8b
```

### GPU (Large Models)
```bash
export EXOSCALE_INSTANCE_TYPE=gpu2.medium
# Cost: ~$0.70/hour
# Good for: llama2:70b, mixtral:8x7b
```

## Troubleshooting

### Instance not starting?
```bash
garuda-exoscale logs
```

### Wrong credentials?
```bash
# Test credentials
garuda-exoscale status
```

### Connection timeout?
Wait 60 seconds for cloud-init to complete after instance creation.

### Cost concerns?
Set shorter idle timeout:
```bash
export EXOSCALE_IDLE_TIMEOUT=300  # 5 minutes
```

## Docker Usage

Create `.env` file:
```bash
EXOSCALE_API_KEY=EXOxxxxxxxxx
EXOSCALE_API_SECRET=xxxxxxxxxxxx
```

Start:
```bash
docker-compose up -d
```

## Need Help?

See full documentation: `docs/EXOSCALE_INTEGRATION.md`
