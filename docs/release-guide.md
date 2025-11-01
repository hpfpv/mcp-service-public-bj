# Release Guide

This guide covers the release process, deployment strategies, and operational procedures for MCP Service Public BJ.

## Release Process

### Version Management

The project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes to MCP tools or API
- **MINOR**: New features, new tools, backward-compatible changes  
- **PATCH**: Bug fixes, performance improvements, documentation updates

### Pre-Release Checklist

#### 1. Code Quality
```bash
# Run full test suite
make test

# Check code formatting and linting
make lint
make format
make mypy

# Verify no security issues
pip-audit

# Check dependencies for updates
pip list --outdated
```

#### 2. Documentation
- [ ] Update README.md with new features
- [ ] Update CHANGELOG.md with release notes
- [ ] Verify all configuration options are documented
- [ ] Check that examples work with current version

#### 3. Testing
```bash
# Integration testing
pytest tests/ -v

# End-to-end testing
make serve-http &
SERVER_PID=$!
sleep 5
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
kill $SERVER_PID

# Docker testing
python -m build --wheel --outdir dist
docker build \
  --build-arg WHEEL_FILE=$(ls dist/*py3-none-any.whl | head -n 1) \
  -t mcp-service-public-bj:test .
docker run --rm mcp-service-public-bj:test --help
```

#### 4. Version Update
```bash
# Update version in pyproject.toml
sed -i 's/version = ".*"/version = "X.Y.Z"/' pyproject.toml

# Update version in main.py
sed -i 's/version=".*"/version="X.Y.Z"/' src/server/main.py

# Commit version bump
git add pyproject.toml src/server/main.py
git commit -m "chore: bump version to X.Y.Z"
```

### Release Steps

#### 1. Create Release Branch
```bash
git checkout -b release/X.Y.Z
git push origin release/X.Y.Z
```

#### 2. Push Release Tag (Triggers GitHub Actions work
```bash
# Create and push tag
git tag -a vX.Y.Z -m "Release version X.Y.Z"
git push origin vX.Y.Z
```

The [`release.yml`](../.github/workflows/release.yml) workflow will automatically:

1. Build Python source and binary distributions, including Linux wheels for x86_64 and aarch64 (via cibuildwheel)
2. Generate build provenance attestations for every artifact
3. Assemble SHA256 checksums and create a GitHub Release with auto-generated notes
4. Build multi-platform Docker images (linux/amd64, linux/arm64) reusing the pre-built wheels, and push them to `ghcr.io/<org>/<repo>` with the following tags:
   - Full semver (`X.Y.Z`)
   - Minor stream (`X.Y`)
   - Major stream (`X`)
   - `latest`

Monitor the workflow from the Actions tab. Once it completes successfully, verify the generated release and container images:

```bash
gh release view vX.Y.Z
docker pull ghcr.io/<org>/<repo>:X.Y.Z
```

#### 3. (Optional) Manual Artifact Validation
```bash
# Download artifacts from the release if manual inspection is required
gh release download vX.Y.Z --pattern "*"

# Verify checksums
cd vX.Y.Z
sha256sum -c SHA256SUMS
```

## Deployment Strategies

### Local Development
```bash
# Install from source
git clone <repository>
cd mcp-service-public-bj
pip install -e .[dev]
mcp-service-public-bj serve
```

### Production Deployment

#### Option 1: Direct Installation
```bash
# Install from PyPI (when available)
pip install mcp-service-public-bj

# Or install from GitHub
pip install git+https://github.com/your-org/mcp-service-public-bj.git

# Configure environment
cp .env.example .env
vim .env

# Run as service
mcp-service-public-bj serve-http --host 0.0.0.0 --port 8000
```

#### Option 2: Docker Deployment
```bash
# Pull image
docker pull ghcr.io/your-org/mcp-service-public-bj:latest

# Run with environment file
docker run -d \
  --name mcp-service-public-bj \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v /opt/mcp-data:/app/data \
  ghcr.io/your-org/mcp-service-public-bj:latest
```

##### Build image from source (if needed)
```bash
# Build wheel once
python -m build --wheel --outdir dist

# Build multi-arch image using the wheel
docker build \
  --build-arg WHEEL_FILE=$(ls dist/*py3-none-any.whl | head -n 1) \
  -t ghcr.io/your-org/mcp-service-public-bj:dev .
```

#### Option 3: Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  mcp-service-public-bj:
    image: mcp-service-public-bj:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - MCP_SP_CACHE_TTL=600
      - MCP_SP_CONCURRENCY=4
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    command: ["serve-http", "--host", "0.0.0.0"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
```

```bash
# Deploy
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f
```

### Kubernetes Deployment

#### Deployment Manifest
```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-service-public-bj
  labels:
    app: mcp-service-public-bj
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mcp-service-public-bj
  template:
    metadata:
      labels:
        app: mcp-service-public-bj
    spec:
      containers:
      - name: mcp-service-public-bj
        image: mcp-service-public-bj:latest
        ports:
        - containerPort: 8000
        env:
        - name: MCP_SP_CACHE_TTL
          value: "600"
        - name: MCP_SP_CONCURRENCY
          value: "4"
        volumeMounts:
        - name: data-volume
          mountPath: /app/data
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: data-volume
        persistentVolumeClaim:
          claimName: mcp-data-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-service-public-bj-service
spec:
  selector:
    app: mcp-service-public-bj
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: ClusterIP
```

```bash
# Deploy to Kubernetes
kubectl apply -f k8s/
kubectl get pods -l app=mcp-service-public-bj
kubectl logs -l app=mcp-service-public-bj -f
```

## Configuration Management

### Environment Variables
```bash
# Core settings
MCP_SP_BASE_URL=https://service-public.bj/
MCP_SP_CACHE_DIR=/app/data/registry
MCP_SP_CONCURRENCY=2
MCP_SP_TIMEOUT=30
MCP_SP_CACHE_TTL=300
MCP_SP_USER_AGENT=MCP-Service-Public-BJ/X.Y.Z

# Optional features
MCP_ENABLED_PROVIDERS=service-public-bj
LOG_LEVEL=INFO

# Security (if needed)
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
```

### Configuration Files
```bash
# Production config
mkdir -p /etc/mcp-service-public-bj
cat > /etc/mcp-service-public-bj/config.env << EOF
MCP_SP_CACHE_TTL=600
MCP_SP_CONCURRENCY=4
LOG_LEVEL=INFO
EOF

# Load in systemd service
Environment=EnvironmentFile=/etc/mcp-service-public-bj/config.env
```

## Monitoring and Observability

### Health Checks
```bash
# Basic health check
curl http://localhost:8000/healthz

# Expected response
{
  "status": "ok",
  "providers": ["service-public-bj"],
  "registry": {
    "service-public-bj": {
      "categories": 15,
      "services": 142
    }
  }
}
```

### Metrics Collection
```bash
# Prometheus metrics
curl http://localhost:8000/metrics

# Key metrics to monitor
# - mcp_tool_invocations_total
# - mcp_tool_duration_seconds
# - mcp_http_requests_total
# - mcp_live_fetch_duration_seconds
```

### Logging
```bash
# Structured JSON logs
export LOG_LEVEL=INFO
mcp-service-public-bj serve-http 2>&1 | jq .

# Log aggregation with fluentd/logstash
# Configure to parse JSON logs and forward to centralized logging
```

### Alerting Rules (Prometheus)
```yaml
# alerts.yml
groups:
- name: mcp-service-public-bj
  rules:
  - alert: MCPServerDown
    expr: up{job="mcp-service-public-bj"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "MCP server is down"
      
  - alert: HighErrorRate
    expr: rate(mcp_tool_invocations_total{status="error"}[5m]) > 0.1
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "High error rate in MCP tools"
      
  - alert: SlowResponseTime
    expr: histogram_quantile(0.95, mcp_tool_duration_seconds) > 10
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Slow MCP tool response times"
```

## Backup and Recovery

### Data Backup
```bash
# Backup registry data
tar -czf mcp-backup-$(date +%Y%m%d).tar.gz data/registry/

# Automated backup script
#!/bin/bash
BACKUP_DIR="/opt/backups/mcp-service-public-bj"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/registry-$DATE.tar.gz data/registry/
find $BACKUP_DIR -name "registry-*.tar.gz" -mtime +7 -delete
```

### Recovery Procedures
```bash
# Restore from backup
tar -xzf mcp-backup-20240101.tar.gz
chown -R appuser:appuser data/registry/

# Verify data integrity
mcp-service-public-bj status --live
```

## Security Considerations

### Network Security
- Run behind reverse proxy (nginx, traefik)
- Use HTTPS in production
- Implement rate limiting
- Configure firewall rules

### Container Security
```dockerfile
# Use non-root user
USER appuser

# Read-only filesystem where possible
--read-only --tmpfs /tmp

# Drop capabilities
--cap-drop=ALL
```

### Access Control
- Implement authentication if exposing HTTP endpoint
- Use network policies in Kubernetes
- Monitor access logs

## Troubleshooting

### Common Issues

#### 1. Service Won't Start
```bash
# Check configuration
mcp-service-public-bj --help

# Verify environment
env | grep MCP_

# Check permissions
ls -la data/registry/
```

#### 2. No Data Returned
```bash
# Test connectivity
curl -I https://service-public.bj/

# Force refresh
mcp-service-public-bj scrape --query "test" --limit 1

# Check logs
tail -f logs/mcp-service-public-bj.log
```

#### 3. Performance Issues
```bash
# Check metrics
curl http://localhost:8000/metrics | grep duration

# Monitor resource usage
docker stats mcp-service-public-bj

# Adjust concurrency
export MCP_SP_CONCURRENCY=1
```

### Debug Commands
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Test specific provider
mcp-service-public-bj status --provider service-public-bj --live

# Validate service data
mcp-service-public-bj scrape --service-id PS00328
```

## Rollback Procedures

### Application Rollback
```bash
# Docker rollback
docker stop mcp-service-public-bj
docker run -d --name mcp-service-public-bj \
  mcp-service-public-bj:previous-version

# Kubernetes rollback
kubectl rollout undo deployment/mcp-service-public-bj
kubectl rollout status deployment/mcp-service-public-bj
```

### Data Rollback
```bash
# Restore previous registry state
cp data/registry/registry.json.backup data/registry/registry.json
systemctl restart mcp-service-public-bj
```

## Performance Optimization

### Scaling Strategies
- Horizontal scaling: Multiple instances behind load balancer
- Vertical scaling: Increase memory/CPU for single instance
- Caching: Increase cache TTL for stable data
- Connection pooling: Optimize HTTP client settings

### Resource Requirements
- **Minimum**: 256MB RAM, 0.25 CPU cores
- **Recommended**: 512MB RAM, 0.5 CPU cores
- **Storage**: 100MB for registry data
- **Network**: Outbound HTTPS access to service-public.bj

This release guide provides comprehensive procedures for deploying, monitoring, and maintaining MCP Service Public BJ in production environments.
