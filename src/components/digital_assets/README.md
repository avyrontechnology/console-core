```
# Digital Asset Integration Guide
Version: 1.0  
Last Updated: January 15, 2025

## Overview
This document provides step-by-step instructions for integrating the Digital Asset codebase into both Maglo and Console services. The integration process ensures proper setup and functionality of Digital Asset features across both platforms.

## Prerequisites
- Git access to the MakunaiGlobal repositories
- Docker installed and configured
- Poetry package manager
- Alembic migration tool
- Appropriate access permissions to both Maglo and Console services

## Installation Steps

### 1. Branch Setup
First, ensure you're working on the correct feature branch:
```bash
git checkout feature-dev-2024
git pull origin feature-dev-2024
```

### 2. Component Setup
Navigate to the components directory:
```bash
cd src/components/
```

### 3. Repository Integration
Clone the Digital Asset repository:
```bash
git clone git@github.com:MakunaiGlobal/digital_assets.git
```

### 4. Dependencies Management
Update the Poetry lock file to ensure all dependencies are properly tracked:
```bash
poetry lock
```

### 5. Container Setup
Build and start the Docker container:
```bash
docker compose up --build
```

### 6. Database Migration
Run the database migration to ensure all required tables and schemas are created:
```bash
alembic upgrade head
```

### 7. Implementation
After completing the above steps, the Digital Asset (DA) features will be ready for use in your development environment.

## Important Notes
- This integration process must be completed for both Maglo and Console services
- Ensure all steps are followed in sequence
- Verify each step is successful before proceeding to the next

## Support
For any issues or questions regarding the integration process, please contact the development team.

## Version History
- 1.0 (Jan 15, 2025): Initial documentation release
```
