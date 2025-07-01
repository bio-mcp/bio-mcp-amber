# Use a base image with conda for easier AMBER installation
FROM condaforge/mambaforge:latest AS amber-base

# Install AMBER via conda-forge
RUN mamba install -c conda-forge ambertools -y && \
    mamba clean --all -y

# Build MCP server layer
FROM python:3.11-slim

# Install system dependencies needed for AMBER tools
RUN apt-get update && apt-get install -y \
    libgfortran5 \
    libgomp1 \
    libblas3 \
    liblapack3 \
    && rm -rf /var/lib/apt/lists/*

# Copy AMBER tools from conda environment
COPY --from=amber-base /opt/conda/bin/tleap /usr/local/bin/
COPY --from=amber-base /opt/conda/bin/pmemd /usr/local/bin/
COPY --from=amber-base /opt/conda/bin/cpptraj /usr/local/bin/
COPY --from=amber-base /opt/conda/bin/sander /usr/local/bin/
COPY --from=amber-base /opt/conda/bin/antechamber /usr/local/bin/

# Copy AMBER data and parameter files
COPY --from=amber-base /opt/conda/dat /opt/amber/dat
COPY --from=amber-base /opt/conda/lib /opt/amber/lib

# Set AMBERHOME environment variable
ENV AMBERHOME=/opt/amber
ENV PATH="${PATH}:${AMBERHOME}/bin"

# Install Python dependencies
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .

# Copy server code
COPY src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 mcp && \
    mkdir -p /tmp/mcp-work && \
    chown -R mcp:mcp /app /tmp/mcp-work

USER mcp

# Set environment variables for MCP server
ENV BIO_MCP_TEMP_DIR=/tmp/mcp-work
ENV BIO_MCP_AMBER_PATH=/usr/local/bin
ENV BIO_MCP_TLEAP_PATH=/usr/local/bin/tleap
ENV BIO_MCP_PMEMD_PATH=/usr/local/bin/pmemd
ENV BIO_MCP_TIMEOUT=3600

# Run the server
CMD ["python", "-m", "src.server"]