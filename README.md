# bio-mcp-amber

MCP (Model Context Protocol) server for AMBER molecular dynamics suite for PDB relaxation.

## Overview

This MCP server provides access to AMBER functionality, allowing AI assistants to perform molecular dynamics simulations and PDB structure relaxation.

## Features

- PDB structure relaxation and energy minimization
- Molecular dynamics simulations for protein structures
- File size limits and timeout protection
- Temporary file management
- Async execution with proper error handling

## Installation

### Using pip

```bash
pip install bio-mcp-amber
```

### From source

```bash
git clone https://github.com/bio-mcp/bio-mcp-amber
cd bio-mcp-amber
pip install -e .
```

## Configuration

Configure your MCP client (e.g., Claude Desktop) by adding to your configuration:

```json
{
  "mcp-servers": {
    "bio-amber": {
      "command": "python",
      "args": ["-m", "bio_mcp_amber"]
    }
  }
}
```

### Environment Variables

- `BIO_MCP_MAX_FILE_SIZE`: Maximum input file size (default: 100MB)
- `BIO_MCP_TIMEOUT`: Command timeout in seconds (default: 300)
- `BIO_MCP_AMBER_PATH`: Path to amber executable
- `BIO_MCP_PMEMD_PATH`: Path to pmemd executable (GPU-accelerated version)

## Usage

Once configured, the AI assistant can use the following tools:

### `amber_relax_pdb`

Perform energy minimization and relaxation of PDB structures using AMBER.

**Parameters:**
- `input_file` (required): Path to input PDB file
- `force_field` (optional): Force field to use (default: ff19SB)
- `steps` (optional): Number of minimization steps (default: 10000)
- `restraints` (optional): Apply positional restraints to backbone atoms

**Example:**
```
Relax structure.pdb using AMBER with ff19SB force field and 10000 minimization steps
```

## Development

### Running tests

```bash
pytest tests/
```

### Building Docker image

```bash
docker build -t bio-mcp-amber .
```

## License

MIT License