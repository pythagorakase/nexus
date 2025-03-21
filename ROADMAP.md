# Migrating Letta to Virtual Environment with Apple Silicon Optimization

This roadmap provides step-by-step instructions for:
1. Continuing the migration of Letta from Docker to a standard Python virtual environment
2. Optimizing Letta for Apple Silicon M4 Max using llama.cpp with Metal support

## PHASE 1: Prerequisites and Environment Setup
- [X] System tools installed
- [X] Apple Silicon configuration verified

## PHASE 2: PostgreSQL Installation with pgvector
- [X] PostgreSQL installed
- [X] pgvector extension installed
- [X] Database user and database created
- [ ] Database schema initialization pending

## PHASE 3: Python Virtual Environment Setup
- [X] Virtual environment created using custom setup_venv.sh
- [X] Python dependencies installed
- [X] Environment configuration set up

## PHASE 4: Database Migration Planning

### 4.1. Develop Migration Strategy
- [ ] Document the existing SQLite database schema
- [ ] Design equivalent PostgreSQL schema with pgvector extensions
- [ ] Plan for data migration from SQLite to PostgreSQL
- [ ] Create mapping between SQLite data types and PostgreSQL equivalents

### 4.2. Configure Letta Database Connection
- [ ] Update Letta configuration to use PostgreSQL database
- [ ] Ensure database connection parameters are correctly set
- [ ] Prepare environment for Alembic migrations

## PHASE 5: llama.cpp Installation with Metal Support

### 5.1. Install and Build llama.cpp
- [X] Clone the llama.cpp repository
- [X] Build with Metal support for Apple Silicon
- [X] Verify Metal acceleration is available and working

### 5.2. Test Metal Support
- [X] Verify Metal GPU acceleration is properly detected
- [X] Perform simple inference tests to confirm functionality
- [X] Check for any potential compatibility issues

### 5.3. Set Up llama.cpp Server
- [ ] Build and configure the server component
- [ ] Verify server functionality
- [ ] Test server-client communication

## PHASE 6: LLM Model Management

### 6.1. Set Up Model Storage
- [ ] Create organized directory structure for models
- [ ] Document model versioning approach
- [ ] Establish model backup strategy

### 6.2. Acquire Compatible Models
- [ ] Identify suitable GGUF format models
- [ ] Select appropriate quantization levels for your use case
- [ ] Download and organize selected models

### 6.3. Validate Model Performance
- [ ] Test models with Metal acceleration
- [ ] Benchmark performance metrics (speed, memory usage)
- [ ] Evaluate output quality and suitability for intended tasks

## PHASE 7: llama.cpp Server Configuration

### 7.1. Configure Server for Optimal Performance
- [ ] Set up server with appropriate Metal parameters
- [ ] Configure context size based on memory capacity
- [ ] Optimize batch size for throughput

### 7.2. Create Service Management
- [ ] Implement automated startup and shutdown procedures
- [ ] Set up logging and monitoring
- [ ] Create health check mechanisms

## PHASE 8: Letta Integration with Local Environment

### 8.1. Environment Configuration
- [ ] Create comprehensive environment configuration
- [ ] Set up persistent environment variables
- [ ] Configure Letta to use local services instead of containers

### 8.2. Server Configuration
- [ ] Create startup procedures for local environment
- [ ] Configure networking for local development
- [ ] Set up integration points with llama.cpp server

## PHASE 9: Server Management

### 9.1. Service Orchestration
- [ ] Establish startup sequence for dependent services
- [ ] Create verification procedures for each service
- [ ] Set up monitoring and alerts

### 9.2. System Verification
- [ ] Implement comprehensive health checks
- [ ] Create diagnostics for troubleshooting
- [ ] Document verification procedures

## PHASE 10: Performance Optimization

### 10.1. GPU Utilization Analysis
- [ ] Monitor and analyze Metal GPU usage patterns
- [ ] Identify bottlenecks and optimization opportunities
- [ ] Document performance baselines

### 10.2. Parameter Optimization
- [ ] Experiment with different Metal configuration parameters
- [ ] Test various model loading strategies
- [ ] Optimize memory usage patterns

### 10.3. Advanced Optimizations
- [ ] Implement model-specific optimizations
- [ ] Test different quantization strategies
- [ ] Explore multi-model loading techniques

## PHASE 11: NEXUS Architecture Implementation

### 11.1. Agent Framework Design
- [x] Design the specialized agent architecture based on NEXUS specification
- [ ] Create agent communication protocols
- [ ] ~~Design the three-tiered memory hierarchy~~ 
	# decided to map this to Letta's existing two tiers for simplicity

### 11.2. Agent Implementation
- [ ] Implement LORE agent for context management
- [ ] Implement PSYCHE agent for character tracking
- [ ] Implement GAIA agent for world state management
- [ ] Implement MEMNON agent for retrieval operations
- [ ] Implement LOGON agent for narrative generation

### 11.3. Memory System Implementation
- [ ] Implement strategic narrative memory tier
- [ ] Implement entity and relationship tracking tier
- [ ] Implement detailed narrative segment storage
- [ ] Create cross-tier integration mechanisms

### 11.4. Turn-Based Workflow Implementation
- [ ] Implement the turn-based flow from user input to narrative generation
- [ ] Create the structured analysis pipeline for narrative content
- [ ] Develop the payload assembly system for context management
- [ ] Implement the adaptive retrievals based on narrative relevance

## PHASE 12: Integration and Testing

### 12.1. System Integration
- [ ] Integrate all components into cohesive workflow
- [ ] Test end-to-end operation
- [ ] Verify seamless communication between components

### 12.2. Performance Testing
- [ ] Conduct load testing under various conditions
- [ ] Measure and optimize response times
- [ ] Verify resource utilization patterns

### 12.3. Narrative Quality Testing
- [ ] Evaluate narrative coherence and continuity
- [ ] Test character consistency mechanisms
- [ ] Assess world-state tracking accuracy

## Troubleshooting Guide

### Database Issues
- Verify PostgreSQL service status
- Check connection parameters
- Validate database schema integrity
- Test query performance

### llama.cpp Issues
- Verify Metal support is active
- Check for memory allocation errors
- Monitor temperature and thermal throttling
- Test with various GPU utilization levels

### Letta Server Issues
- Verify environment configuration
- Check dependency services
- Review log files for errors
- Confirm networking configuration

### Performance Issues
- Monitor memory usage patterns
- Analyze GPU utilization
- Evaluate model size vs. performance tradeoffs
- Consider quantization adjustments